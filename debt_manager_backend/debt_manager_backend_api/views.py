import logging
from datetime import datetime
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Sum, Q
from django.template.response import SimpleTemplateResponse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from drf_yasg import openapi
from oauth2_provider.contrib.rest_framework import TokenHasReadWriteScope
from rest_framework.response import Response
from rest_framework import permissions, status, exceptions, filters
from rest_framework.reverse import reverse
from rest_framework.viewsets import GenericViewSet
from rest_framework.views import APIView
from rest_framework import viewsets, mixins
from .models import Debtor, Transaction, CurrencyOwner
from .serializers import DebtorSerializer, TransactionSerializer, UserRegistrationSerializer, \
    RecaptchaRequestSerializer, RecaptchaResponseSerializer, SwaggerUserRegistrationSerializer
from .pagination import DebtorPagination, TransactionPagination
from .permissions import DebtorPermission, IsAuthenticatedOrCreateOnly
from rest_framework.decorators import action
from django.http import HttpResponse
import mimetypes
import xlsxwriter
import requests
from io import BytesIO
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.contrib.sites.shortcuts import get_current_site
from .tokens import account_activation_token
from django.conf import settings
from drf_yasg.utils import swagger_auto_schema
from .swagger import SwaggerAutoSchemaWithoutParam

lh = logging.getLogger('django')
mimetypes.init()
User = get_user_model()


# Create your views here.

class ReportGenerator:

    def __init__(self, ext, pk):
        extension = {'xlsx': self.xlsx_report}
        self.debtor = pk
        try:
            self._report_generator = extension[ext]
        except KeyError:
            raise KeyError

    def xlsx_report(self, pk):
        tr_list = Transaction.objects.filter(is_active=True, debtor=pk).order_by('-date')
        if not tr_list:
            raise IndexError
        debtor_name = tr_list[0].debtor.name
        balance = tr_list.aggregate(Sum('sum'))
        currency = CurrencyOwner.objects.get(owner=tr_list[0].debtor.owner, current=True).currency.name
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, options={'default_format_properties': {'align': 'justify'}})
        worksheet = workbook.add_worksheet('balance sheet report')
        worksheet.set_column(0, 0, 6)
        worksheet.set_column(1, 1, 10)
        worksheet.set_column(2, 6, 15)
        worksheet.write_string(0, 5, 'debtor name:')
        worksheet.write_string(0, 6, debtor_name)
        worksheet.write_string(1, 5, 'balance:')
        worksheet.write_number(1, 6, balance['sum__sum'])
        column_name = ['id', 'date', 'change', 'currency', 'comment']
        for i, v in enumerate(column_name):
            worksheet.write_string(0, i, v)
        for row, v in enumerate(tr_list, start=1):
            worksheet.write_number(row, 0, v.id)
            date_format = workbook.add_format({'num_format': 'dd-mm-yyyy'})
            worksheet.write(row, 1, v.date, date_format)
            if v.sum > 0:
                worksheet.write_string(row, 2, f'gave a loan of {v.sum}')
            else:
                worksheet.write_string(row, 2, f'borrowed {abs(v.sum)}')
            worksheet.write_string(row, 3, currency)
            worksheet.write_string(row, 4, v.comment)
        workbook.close()
        return output

    def get_report(self):
        return self._report_generator(self.debtor)


class DebtorViewSet(viewsets.ModelViewSet):
    serializer_class = DebtorSerializer
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope, DebtorPermission]
    pagination_class = DebtorPagination
    filter_backends = [filters.SearchFilter]
    search_fields = ['name']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            # queryset just for schema generation metadata
            return Debtor.objects.none()
        return Debtor.objects.filter(is_active=True, owner=self.request.user).order_by('id')

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=['is_active'])
        Transaction.objects.filter(debtor=instance).update(is_active=False)

    @swagger_auto_schema(manual_parameters=[openapi.Parameter('extension', openapi.IN_QUERY,
                                                              description="report file extention",
                                                              type=openapi.TYPE_STRING,
                                                              required=True)],
                         responses={200: openapi.Response('Report file',
                                                          schema=openapi.Schema(type=openapi.TYPE_FILE))})
    @action(detail=True, methods=['get'], url_path='report', url_name='report')
    def get_file_report(self, request, pk=None):
        try:
            ext = request.GET['extension']
        except KeyError:
            lh.error('missing get parameter: extension')
            raise exceptions.ParseError(detail='missing get parameter: extension')
        try:
            debtor = Debtor.objects.get(id=pk)
        except Debtor.DoesNotExist:
            raise exceptions.NotFound()
        self.check_object_permissions(self.request, debtor)
        try:
            report_obj = ReportGenerator(ext, debtor).get_report()
        except KeyError:
            lh.error(f'report format not supported: {ext}')
            raise exceptions.UnsupportedMediaType(ext)
        except IndexError:
            lh.error('The debtor has no transactions')
            raise exceptions.NotFound(detail='The debtor has no transactions')
        report_obj.seek(0)
        try:
            mimetypes.types_map[f'.{ext}']
        except KeyError:
            lh.error('mimetype is not in mime.types file or windows registry')
            raise exceptions.UnsupportedMediaType(ext)
        response = HttpResponse(report_obj.read(), mimetypes.types_map[f'.{ext}'])
        report_date = datetime.now().strftime('%d-%m_%Y')
        response['Content-Disposition'] = f'attachment; filename="report_{report_date}.{ext}"'
        return response


class TransactionViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    serializer_class = TransactionSerializer
    pagination_class = TransactionPagination

    def call_debtor_check(self):
        try:
            debtor = Debtor.objects.get(id=self.kwargs['debtor_pk'])
        except Debtor.DoesNotExist:
            raise exceptions.NotFound()
        debtor_permission_inst = DebtorPermission()
        if not debtor_permission_inst.has_object_permission(self.request, self, debtor):
            self.permission_denied(
                self.request, message=getattr(DebtorPermission, 'message', None)
            )
        return debtor

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            # queryset just for schema generation metadata
            return Transaction.objects.none()
        debtor = self.call_debtor_check()
        # add context using in paginator class
        self.request.parser_context['debtor'] = debtor
        return Transaction.objects.filter(is_active=True, debtor=self.kwargs['debtor_pk']).order_by('-date')

    def create(self, request, *args, **kwargs):
        debtor = self.call_debtor_check()
        self.request.parser_context['debtor'] = debtor
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        debtor = self.call_debtor_check()
        self.request.parser_context['debtor'] = debtor
        tr_id = self.request.parser_context['kwargs']['pk']
        partial = kwargs.pop('partial', False)
        instance = Transaction.objects.get(id=tr_id)
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        if getattr(instance, '_prefetched_objects_cache', None):
            # If 'prefetch_related' has been applied to a queryset, we need to
            # forcibly invalidate the prefetch cache on the instance.
            instance._prefetched_objects_cache = {}

        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        _ = self.call_debtor_check()
        tr_id = self.request.parser_context['kwargs']['pk']
        instance = Transaction.objects.get(id=tr_id)
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=['is_active'])


class UserViewSet(GenericViewSet, mixins.CreateModelMixin):
    serializer_class = UserRegistrationSerializer
    queryset = User.objects.all()
    permission_classes = [IsAuthenticatedOrCreateOnly]

    @swagger_auto_schema(auto_schema=SwaggerAutoSchemaWithoutParam, extra_overrides={'exluded_params': ['page']},
                         responses={200: SwaggerUserRegistrationSerializer})
    @action(detail=False, methods=['get'], url_path='current', url_name='current')
    def get_current_user(self, request):
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

    def perform_create(self, serializer):
        new_user = serializer.save()
        current_site = get_current_site(self.request)
        html_content = render_to_string('acc_active_email.html', {
            'user': new_user.username,
            'domain': current_site.domain,
            'uid': urlsafe_base64_encode(force_bytes(new_user.pk)),
            'token': account_activation_token.make_token(new_user),
        })
        reverse_user = reverse("user-activate", kwargs={"uidb64":urlsafe_base64_encode(force_bytes(new_user.pk)),
                                                        "token": account_activation_token.make_token(new_user)})
        text_content = f'Здравствуйте, {new_user.username}\r. Этот емаил был указан при регистрации в сервисе' \
                       f' debt manager. Для активации аккаунта пройдите по ссылке: ' \
                       f'http://{current_site.domain}{reverse_user}'
        msg = EmailMultiAlternatives('debtor manager registration', text_content, settings.EMAIL_FROM, [new_user.email])
        msg.attach_alternative(html_content, "text/html")
        msg.send()

    @swagger_auto_schema(auto_schema=None)
    @action(detail=False, methods=['get'],
            url_path='activate/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,32})',
            url_name='activate',
            permission_classes=[permissions.AllowAny])
    def activate_user(self, request, uidb64, token):
        try:
            uid = urlsafe_base64_decode(uidb64)
            user = User.objects.get(pk=uid)
        except(TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None
        if user is not None and account_activation_token.check_token(user, token):
            self.user_confirmation(user)
            return SimpleTemplateResponse('acc_activation_succes.html', context={'front_url': settings.FRONT_MAIN_PAGE},
                                          status=status.HTTP_200_OK)
        else:
            return SimpleTemplateResponse('acc_activation_error.html', status=status.HTTP_403_FORBIDDEN)

    def user_confirmation(self, user):
        with transaction.atomic():
            user.is_active = True
            user.save()
            user_to_delete = User.objects.filter(
                (Q(username__iexact=user.username) | Q(email__iexact=user.email)),
                is_active=False
            )
            currency_to_check = set()
            for u in user_to_delete:
                [currency_to_check.add(i.currency) for i in CurrencyOwner.objects.filter(owner=u)]
                u.delete()
            for cur in currency_to_check:
                if not CurrencyOwner.objects.filter(currency=cur):
                    cur.is_active = False
                    cur.save()


class RecaptchaAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    @swagger_auto_schema(request_body=RecaptchaRequestSerializer, responses={200: RecaptchaResponseSerializer})
    def post(self, request, *args, **kwargs):
        serialized = RecaptchaRequestSerializer(data=request.data)
        if not serialized.is_valid():
            raise exceptions.ValidationError(serialized.errors)
        serialized.validated_data['secret'] = settings.GOOGLE_RECAPTCHA_SECRET_KEY
        google_response = self.verify_captcha(serialized.validated_data)
        response, http_status = self.google_response_parser(google_response)
        return Response(response, status=http_status)

    def google_response_parser(self, response):
        if not response:
            msg = 'Error connecting to recaptcha check server'
            response = {
                "success": False,
                "error-codes": [msg]
            }
            return response, status.HTTP_400_BAD_REQUEST
        if not response.get('success'):
            err = response.get("error-codes")
            lh.error(f'Wrong or invalide captcha token: {err}')
            return response, status.HTTP_400_BAD_REQUEST
        if response.get('score', 0) < settings.GOOGLE_RECAPTCHA_THRESHOLD_SCORE:
            score = response.get('score', 0)
            lh.error(f'Possible bot: treshold {settings.GOOGLE_RECAPTCHA_THRESHOLD_SCORE} > {score}')
            response['success'] = False
            return response, status.HTTP_400_BAD_REQUEST
        return response, status.HTTP_200_OK

    def verify_captcha(self, data):
        try:
            r = requests.post(settings.GOOGLE_RECAPTCHA_URL, data=data)
            r.raise_for_status()
        except requests.exceptions.ReadTimeout:
            lh.error("request read timeout")
            return
        except requests.exceptions.ConnectTimeout:
            lh.error("request connection timeout")
            return
        except requests.exceptions.ConnectionError as err:
            lh.error(f"connection error: {err}")
            return
        except requests.exceptions.HTTPError as err:
            lh.error(f"HTTP error. {err}")
            return
        except requests.exceptions as err:
            lh.error(f"Unhandled error: {err}")
            return
        return r.json()
