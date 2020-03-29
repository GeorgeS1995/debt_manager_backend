from django.db import models
from django.conf import settings
from datetime import date
from django.contrib.auth.models import AbstractUser


# Create your models here.

class UniqEmailUser(AbstractUser):
    email = models.EmailField(unique=True)


class Currency(models.Model):
    name = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)


class CurrencyOwner(models.Model):
    currency = models.ForeignKey(Currency, on_delete=models.DO_NOTHING)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.DO_NOTHING)
    current = models.BooleanField()


class Debtor(models.Model):
    name = models.CharField(max_length=255)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.DO_NOTHING)
    is_active = models.BooleanField(default=True)


class Transaction(models.Model):
    date = models.DateField(default=date.today)
    sum = models.FloatField()
    comment = models.TextField()
    debtor = models.ForeignKey(Debtor, on_delete=models.DO_NOTHING)
    is_active = models.BooleanField(default=True)
