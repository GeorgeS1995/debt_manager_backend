import logging
from django.core.exceptions import ValidationError
from rest_framework import serializers
from .models import Debtor, Transaction, Currency, CurrencyOwner
from django.db.models import Sum
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import IntegrityError, transaction

lh = logging.getLogger('django')
User = get_user_model()

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


class UserRegistrationSerializer(serializers.HyperlinkedModelSerializer):
    password1 = serializers.CharField(write_only=True)
    password2 = serializers.CharField(write_only=True)
    currency = serializers.CharField()

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'password1', 'password2', 'currency']

    def validate(self, data):
        if data['password1'] == data['password2']:
            try:
                validate_password(data['password1'])
            except ValidationError as err:
                lh.error(f'Unsuccessful attempt to register: {err}')
                raise serializers.ValidationError(f'Unsuccessful attempt to register: {err}')
            return data
        raise serializers.ValidationError("Passwords do not match")

    def create(self, validated_data):
        password = validated_data['password1']
        currency = validated_data['currency']
        del validated_data['password1']
        del validated_data['password2']
        del validated_data['currency']
        with transaction.atomic():
            user = User.objects.create(**validated_data)
            user.is_active = False
            user.set_password(password)
            user.save()
            new_currency = Currency.objects.filter(name=currency)
            if not new_currency.exists():
                new_currency = Currency.objects.create(name=currency)
                new_currency.save()
            else:
                new_currency = new_currency[0]
            new_currency_owner = CurrencyOwner.objects.create(currency=new_currency, owner=user, current=True)
            new_currency_owner.save()
        return user

    def to_representation(self, instance):
        del self._validated_data['password1']
        del self._validated_data['password2']
        return self._validated_data


