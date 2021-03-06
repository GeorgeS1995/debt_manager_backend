import logging
from django.core.exceptions import ValidationError
from rest_framework import serializers
from .models import Debtor, Transaction, Currency, CurrencyOwner
from django.db.models import Sum
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction

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

    def validate_sum(self, value):
        if not value:
            raise serializers.ValidationError('zero amount')
        return value

    def create(self, validated_data):
        debtor = self.context['request'].parser_context['debtor']
        validated_data['debtor'] = Debtor.objects.get(id=debtor.id)
        return Transaction.objects.create(**validated_data)


class CurrencyRelatedField(serializers.RelatedField):

    def get_attribute(self, instance):
        return instance

    def to_representation(self, value):
        return CurrencyOwner.objects.filter(owner__username=value.username, current=True)[0].currency.name

    def to_internal_value(self, data):
        return data


class UserRegistrationSerializer(serializers.HyperlinkedModelSerializer):
    password1 = serializers.CharField(write_only=True)
    password2 = serializers.CharField(write_only=True)
    currency = CurrencyRelatedField(queryset=CurrencyOwner.objects.all())

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'password1', 'password2', 'currency']

    def validate_username(self, value):
        if User.objects.filter(is_active=True, username=value):
            raise serializers.ValidationError('Not uniq username')
        return value

    def validate_email(self, value):
        if User.objects.filter(is_active=True, email=value):
            raise serializers.ValidationError('Not uniq email')
        return value

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
            new_currency, created = Currency.objects.update_or_create(name=currency, defaults={'is_active': True})
            new_currency_owner = CurrencyOwner.objects.create(currency=new_currency, owner=user, current=True)
            new_currency_owner.save()
        return user


class SwaggerUserRegistrationSerializer(serializers.Serializer):
    username = serializers.CharField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    email = serializers.EmailField()
    currency = serializers.CharField()


class RecaptchaRequestSerializer(serializers.Serializer):
    response = serializers.CharField()


class RecaptchaResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    challenge_ts = serializers.DateTimeField()
    hostname = serializers.CharField()
    score = serializers.FloatField()
