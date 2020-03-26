import logging
from django.db.models import Sum
from oauth2_provider.contrib.rest_framework import TokenHasReadWriteScope
from rest_framework.response import Response
from rest_framework import permissions, status
from rest_framework import viewsets
from .models import Debtor, Transaction, Currency
from .serializers import DebtorSerializer, TransactionSerializer
from .pagination import DebtorPagination, TransactionPagination
from .permissions import DebtorPermission
from rest_framework.decorators import action
from rest_framework import serializers
from django.http import HttpResponse
import mimetypes
import xlsxwriter
from io import BytesIO

lh = logging.getLogger('django')


# Create your views here.

class ReportGenerator:

    def __init__(self, ext, pk):
        extension = {'xlsx': self.xlsx_report}
        try:
            self.generated_report = extension[ext](pk)
        except KeyError:
            raise KeyError

    def xlsx_report(self, pk):
        tr_list = Transaction.objects.filter(is_active=True, debtor=pk).order_by('-date')
        if not tr_list:
            raise IndexError
        debtor_name = tr_list[0].debtor.name
        balance = tr_list.aggregate(Sum('sum'))
        currency = Currency.objects.get(owner=tr_list[0].debtor.owner, current=True).name
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
        return self.generated_report


class DebtorViewSet(viewsets.ModelViewSet):
    serializer_class = DebtorSerializer
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    pagination_class = DebtorPagination

    def get_queryset(self):
        return Debtor.objects.filter(is_active=True, owner=self.request.user).order_by('id')

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=['is_active'])
        Transaction.objects.filter(debtor=instance).update(is_active=False)

    @action(detail=True, methods=['get'], url_path='report', url_name='report')
    def get_file_report(self, request, pk=None):
        try:
            ext = request.GET['extension']
        except KeyError:
            lh.error('missing get parameter: extension')
            raise serializers.ValidationError('missing get parameter: extension')
        try:
            report_obj = ReportGenerator(ext, pk).get_report()
        except KeyError:
            lh.error(f'report format not supported: {ext}')
            raise serializers.ValidationError(f'report format not supported: {ext}')
        except IndexError:
            lh.error('The debtor has no transactions')
            raise serializers.ValidationError('The debtor has no transactions')
        report_obj.seek(0)
        return HttpResponse(report_obj.read(), mimetypes.types_map[f'.{ext}'])


class TransactionViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope, DebtorPermission]
    serializer_class = TransactionSerializer
    pagination_class = TransactionPagination

    def call_debtor_check(self):
        debtor = Debtor.objects.get(id=self.kwargs['debtor_pk'])
        self.check_object_permissions(self.request, debtor)
        return debtor

    def get_queryset(self):
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
