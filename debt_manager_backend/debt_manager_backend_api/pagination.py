import logging
from django.db.models import Sum
from rest_framework import pagination
from rest_framework.response import Response
from .models import Transaction, CurrencyOwner
from rest_framework import serializers

lh = logging.getLogger('django')


class PagiantionWithBalance(pagination.PageNumberPagination):
    page_size_query_param = 'size'

    def get_current_currency(self):
        user = self.request.user
        try:
            currency = CurrencyOwner.objects.get(owner=user, current=True).currency
        except CurrencyOwner.DoesNotExist:
            lh.warning('active currency not configured for user')
            raise serializers.ValidationError('active currency not configured for user')
        return currency.name

    def get_total_balance(self):
        pass


class DebtorPagination(PagiantionWithBalance):

    def get_paginated_response(self, data):
        tb = self.get_total_balance()
        currency = self.get_current_currency()
        return Response({
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'count': self.page.paginator.count,
            'total_balance': tb,
            'currency': currency,
            'results': data
        })

    def get_total_balance(self):
        user = self.request.user
        balance = Transaction.objects.filter(is_active=True, debtor__owner=user).aggregate(Sum('sum'))
        return balance['sum__sum']


class TransactionPagination(PagiantionWithBalance):

    def get_paginated_response(self, data):
        tb = self.get_total_balance()
        currency = self.get_current_currency()
        debtor = self.get_debtor()
        return Response({
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'count': self.page.paginator.count,
            'total_balance': tb,
            'currency': currency,
            'debtor_props': debtor,
            'results': data
        })

    def get_total_balance(self):
        debtor_id = self.request.parser_context['kwargs']['debtor_pk']
        balance = Transaction.objects.filter(is_active=True, debtor=debtor_id).aggregate(Sum('sum'))
        return balance['sum__sum']

    def get_debtor(self):
        debtor = self.request.parser_context['debtor']
        return {'name': debtor.name}
