from django.db import models
from django.contrib.auth.models import User
from datetime import date


# Create your models here.

class Currency(models.Model):
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    owner = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    current = models.BooleanField()


class Debtor(models.Model):
    name = models.CharField(max_length=255)
    owner = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    is_active = models.BooleanField(default=True)


class Transaction(models.Model):
    date = models.DateField(default=date.today)
    sum = models.FloatField()
    comment = models.TextField()
    debtor = models.ForeignKey(Debtor, on_delete=models.DO_NOTHING)
    is_active = models.BooleanField(default=True)
