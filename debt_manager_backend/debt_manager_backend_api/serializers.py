from rest_framework import serializers
from .models import Debtor, Transaction
from django.db.models import Sum


class DebtorSerializer(serializers.HyperlinkedModelSerializer):
    balance = serializers.SerializerMethodField()

    class Meta:
        model = Debtor
        fields = ['id', 'name', 'balance']

    def get_balance(self, obj):
        balance = Transaction.objects.filter(is_active=True, debtor=obj.id).aggregate(Sum('sum'))
        return balance['sum__sum']

    def create(self, validated_data):
        user = self.context['request'].user
        name = validated_data['name']
        return Debtor.objects.create(name=name, owner=user)


class TransactionSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Transaction
        fields = ['id', 'date', 'sum', 'comment']

    def create(self, validated_data):
        debtor = self.context['request'].parser_context['debtor']
        validated_data['debtor'] = Debtor.objects.get(id=debtor.id)
        return Transaction.objects.create(**validated_data)
