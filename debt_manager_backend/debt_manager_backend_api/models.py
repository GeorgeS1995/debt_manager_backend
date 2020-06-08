from django.db import models
from django.conf import settings
from datetime import date
from django.contrib.auth.models import AbstractUser


# Create your models here.

class UniqEmailUser(AbstractUser):
    email = models.EmailField()
    username = models.CharField(max_length=150)


class Currency(models.Model):
    name = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)


class CurrencyOwner(models.Model):
    currency = models.ForeignKey(Currency, on_delete=models.CASCADE)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    current = models.BooleanField()


class Debtor(models.Model):
    name = models.CharField(max_length=255)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.DO_NOTHING)
    is_active = models.BooleanField(default=True)


class Transaction(models.Model):
    date = models.DateField(default=date.today)
    sum = models.FloatField()
    comment = models.TextField(blank=True)
    debtor = models.ForeignKey(Debtor, on_delete=models.DO_NOTHING)
    is_active = models.BooleanField(default=True)
