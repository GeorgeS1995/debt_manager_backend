from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase, APIClient
from oauth2_provider.models import AccessToken, Application
from django.utils import timezone
from .models import Currency, Debtor, Transaction, CurrencyOwner
from rest_framework.reverse import reverse
from rest_framework import status
import shutil
from io import BytesIO
import mimetypes
import os
from django.conf import settings
import xlrd
from django.core import mail
import re

User = get_user_model()


# Create your tests here.

class ApiUserTestClient(APITestCase):
    """
    Helper base class for API test
    """

    client = APIClient()

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not os.path.exists(os.path.join(settings.BASE_DIR, 'test_temp')):
            os.makedirs(os.path.join(settings.BASE_DIR, 'test_temp'))

    @classmethod
    def setUpTestData(cls):
        users_param = [
            {
                "username": 'test@test.com',
                "email": 'test@test.com',
                "is_active": True,
            },
            {
                "username": 'second_user@test.com',
                "email": 'second_user@test.com',
                "is_active": True,
            }
        ]

        for u in users_param:
            new_user = User.objects.create(**u)
            new_user.save()
            if new_user.id == 1:
                cls.user = new_user

        cls.application = Application.objects.create(
            name="Test Application",
            redirect_uris="http://localhost http://example.com http://example.org",
            user=cls.user,
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
        )

        cls.access_token = AccessToken.objects.create(
            user=cls.user,
            scope="read write",
            expires=timezone.now() + timezone.timedelta(seconds=300),
            token="secret-access-token-key",
            application=cls.application
        )
        cls.access_token.save()
        cls.application.save()

        cls.client.force_authenticate(user=cls.user, token=cls.access_token.token)

        currency = Currency.objects.create(name='руб')
        currency.save()

        currency_owner = CurrencyOwner.objects.create(currency=currency, owner=cls.user, current=True)
        currency_owner.save()

        debtor_name = ['test1', 'test2']
        for name in debtor_name:
            debtor = Debtor.objects.create(name=name, owner_id=1)
            debtor.save()

        inactive_debtor = Debtor.objects.create(name='inactive_debtor', is_active=False, owner_id=1)
        inactive_debtor.save()

        inactive_debtor = Debtor.objects.create(name='user2_debtor', owner_id=2)
        inactive_debtor.save()

        debtor_without_tr = Debtor.objects.create(name='empty_debtor', owner_id=1)
        debtor_without_tr.save()

        transaction_param = [
            {'date': '2020-03-03', 'sum': -3, 'comment': 'c1', 'debtor_id': 1},
            {'date': '2020-03-03', 'sum': 4, 'comment': 'c2', 'debtor_id': 1},
            {'date': '2020-03-03', 'sum': 1, 'comment': 'c3', 'debtor_id': 2},
            {'date': '2020-03-03', 'sum': 10, 'comment': 'c4', 'debtor_id': 4},
        ]

        for tp in transaction_param:
            transaction = Transaction.objects.create(**tp)
            transaction.save()

        cls.transaction_list = {
            "next": None,
            "previous": None,
            "count": 2,
            "total_balance": 1.0,
            "currency": "руб",
            "debtor_props": {
                "name": "test1"
            },
            "results": [
                {
                    "id": 1,
                    "date": "2020-03-03",
                    "sum": -3.0,
                    "comment": "c1"
                },
                {
                    "id": 2,
                    "date": "2020-03-03",
                    "sum": 4.0,
                    "comment": "c2"
                }
            ]
        }

    def setUp(self):
        self.login()

    def tearDown(self):
        self.logout()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(os.path.join(settings.BASE_DIR, 'test_temp'))
        super().tearDownClass()

    def login(self):
        self.client.credentials(Authorization='Bearer {}'.format(self.access_token.token))

    def logout(self):
        self.token = None


class DebtorViewSetTestCase(ApiUserTestClient):

    def setUp(self):
        super().setUp()

        self.list_debtors_page_1 = {
            "next": "http://testserver/api/v1/debtor/?page=2&size=1",
            "previous": None,
            "count": 3,
            "total_balance": 2.0,
            "currency": "руб",
            "results": [
                {
                    "id": 1,
                    "name": "test1",
                    "balance": 1.0
                }
            ]
        }

        self.list_debtors_page_2 = {
            "next": 'http://testserver/api/v1/debtor/?page=3&size=1',
            "previous": "http://testserver/api/v1/debtor/?size=1",
            "count": 3,
            "total_balance": 2.0,
            "currency": "руб",
            "results": [
                {
                    "id": 2,
                    "name": "test2",
                    "balance": 1.0
                }
            ]
        }

        self.active_currency_not_set_error = [
            'active currency not configured for user'
        ]

        self.new_debtor = ['test3', True, 'test@test.com']
        self.updated_test1 = {'id': 1, 'name': 'test1_new_name', 'balance': 1.0}

        self.debtor_list_after_delete = {
            "next": None,
            "previous": None,
            "count": 2,
            "total_balance": 1.0,
            "currency": "руб",
            "results": [
                {
                    "id": 2,
                    "name": "test2",
                    "balance": 1.0
                },
                {
                    "id": 5,
                    "name": "empty_debtor",
                    "balance": None
                }
            ]
        }

        self.missing_get_parameter = [
            'missing get parameter: extension'
        ]

        self.format_not_supported = [
            'report format not supported: exe'
        ]

        self.debtor_without_transaction = [
            'The debtor has no transactions'
        ]

        # select extension for testing
        self.switch_extention_func = {'xlsx': self.xlsx_chech}

    def xlsx_chech(self):
        rb = xlrd.open_workbook(os.path.join(settings.BASE_DIR, 'test_temp', f'response.xlsx'))
        datemode = rb.datemode
        sh = rb.sheet_by_name('balance sheet report')
        title = sh.row(0)
        self.assertEqual(title[6].value, self.transaction_list['debtor_props']['name'])
        for i, tr in enumerate(self.transaction_list['results'], start=1):
            r = sh.row(i)
            for i_prop, prop in enumerate(tr.values()):
                # change assert scenario
                if i_prop == 1:
                    d = xlrd.xldate_as_datetime(r[i_prop].value, datemode).strftime('%Y-%m-%d')
                    self.assertEqual(d, prop)
                elif i_prop == 2:
                    if prop > 0:
                        change = f'gave a loan of {prop}'
                    else:
                        change = f'borrowed {abs(prop)}'
                    self.assertEqual(r[i_prop].value, change)
                elif i_prop == 3:
                    self.assertEqual(r[i_prop].value, self.transaction_list['currency'])
                else:
                    self.assertEqual(r[i_prop].value, prop)
            if i == 1:
                self.assertEqual(r[6].value, self.transaction_list['total_balance'])

    def test_get_debtor_list(self):
        response = self.client.get(reverse('debtor-list'), {'page': 1, 'size': 1})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, self.list_debtors_page_1)

        response = self.client.get(reverse('debtor-list'), {'page': 2, 'size': 1})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, self.list_debtors_page_2)

    def test_get_debtor_list_active_currency_not_set(self):
        CurrencyOwner.objects.filter(current=True).update(current=False)
        response = self.client.get(reverse('debtor-list'), {'page': 1, 'size': 1})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, self.active_currency_not_set_error)

    def test_create_debtor(self):
        response = self.client.post(reverse('debtor-list'), {'name': 'test3'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        without_id = response.data.copy()
        del without_id['id']
        self.assertEqual(without_id, {'name': 'test3', 'balance': None})
        db = Debtor.objects.get(id=response.data['id'])
        db_data = [db.name, db.is_active, db.owner.username]
        self.assertEqual(db_data, self.new_debtor)

    def test_change_debtor(self):
        response = self.client.put(reverse('debtor-detail', args=(1,)), {"name": "test1_new_name"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, self.updated_test1)

        response = self.client.patch(reverse('debtor-detail', args=(1,)), {"name": "test1_new_name"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, self.updated_test1)

    def test_delete_debtor(self):
        response = self.client.delete(reverse('debtor-detail', args=(1,)))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        debtor = Debtor.objects.get(id=1)
        self.assertFalse(debtor.is_active)
        debtor_transaction = Transaction.objects.filter(debtor=debtor)
        for tr in debtor_transaction:
            self.assertFalse(tr.is_active)

        response = self.client.get(reverse('debtor-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, self.debtor_list_after_delete)

    def test_report_allowed_method(self):
        response = self.client.post(reverse('debtor-report', args=(1,)), {'extension': 'xlsx'})
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        response = self.client.patch(reverse('debtor-report', args=(1,)), {'extension': 'xlsx'})
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        response = self.client.delete(reverse('debtor-report', args=(1,)), {'extension': 'xlsx'})
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        response = self.client.put(reverse('debtor-report', args=(1,)), {'extension': 'xlsx'})
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_report_missing_extension_error(self):
        response = self.client.get(reverse('debtor-report', args=(1,)))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, self.missing_get_parameter)

    def test_report_not_supported_format(self):
        response = self.client.get(reverse('debtor-report', args=(1,)), {'extension': 'exe'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, self.format_not_supported)

    def test_report_debtor_has_not_transaction(self):
        response = self.client.get(reverse('debtor-report', args=(5,)), {'extension': 'xlsx'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, self.debtor_without_transaction)

    def test_report_xlsx(self):
        response = self.client.get(reverse('debtor-report', args=(1,)), {'extension': 'xlsx'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        byte_obj = BytesIO(response.content)

        ext = mimetypes.guess_extension(response._headers['content-type'][1])
        with open(os.path.join(settings.BASE_DIR, 'test_temp', f'response{ext}'), 'wb') as f:
            shutil.copyfileobj(byte_obj, f)

        self.switch_extention_func[ext[1:]]()


class TransactionViewSetTestCase(ApiUserTestClient):

    def setUp(self):
        super().setUp()

        self.transaction_list_with_new = {
            "next": 'http://testserver/api/v1/debtor/1/transaction/?page=2&size=1',
            "previous": None,
            "count": 3,
            "total_balance": -2.0,
            "currency": "руб",
            "debtor_props": {
                "name": "test1"
            },
            "results": [
                {
                    "id": 5,
                    "date": "2020-04-03",
                    "sum": -3.0,
                    "comment": "c3"
                }
            ]
        }

        self.new_transaction = {
            "date": "2020-04-03",
            "sum": -3.0,
            "comment": "c3"
        }

        self.deleted_debtor = {
            "detail": "You are not the owner of the object or object does not exist"
        }

        self.update_transaction_request = {
            "date": "2020-04-04",
            "sum": -4.0,
            "comment": "test renew comment"
        }

        self.update_transaction_response = {
            "id": 1,
            "date": "2020-04-04",
            "sum": -4.0,
            "comment": "test renew comment"
        }

        self.transaction_list_update = {
            "next": None,
            "previous": None,
            "count": 2,
            "total_balance": 0.0,
            "currency": "руб",
            "debtor_props": {
                "name": "test1"
            },
            "results": [
                {
                    "id": 1,
                    "date": "2020-04-04",
                    "sum": -4.0,
                    "comment": "test renew comment"
                },
                {
                    "id": 2,
                    "date": "2020-03-03",
                    "sum": 4.0,
                    "comment": "c2"
                }
            ]
        }

        self.transaction_list_delete = {
            "next": None,
            "previous": None,
            "count": 1,
            "total_balance": 4.0,
            "currency": "руб",
            "debtor_props": {
                "name": "test1"
            },
            "results": [
                {
                    "id": 2,
                    "date": "2020-03-03",
                    "sum": 4.0,
                    "comment": "c2"
                }
            ]
        }

    def test_get_transaction_list(self):
        response = self.client.get(reverse('debtor-transaction-list', args=(1,)), {'page': 1, 'size': 2})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, self.transaction_list)

        response = self.client.get(reverse('debtor-transaction-list', args=(3,)), {'page': 1, 'size': 2})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data, self.deleted_debtor)

    def test_create_transaction(self):
        response = self.client.post(reverse('debtor-transaction-list', args=(1,)), self.new_transaction)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self.client.get(reverse('debtor-transaction-list', args=(1,)), {'page': 1, 'size': 1})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, self.transaction_list_with_new)

        response = self.client.post(reverse('debtor-transaction-list', args=(3,)), self.new_transaction)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data, self.deleted_debtor)

    def test_update_transaction(self):
        response = self.client.put(reverse('debtor-transaction-detail', args=(1, 1)), self.update_transaction_request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, self.update_transaction_response)

        response = self.client.get(reverse('debtor-transaction-list', args=(1,)), {'page': 1, 'size': 2})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, self.transaction_list_update)

        response = self.client.put(reverse('debtor-transaction-detail', args=(3, 3)), self.new_transaction)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data, self.deleted_debtor)

        response = self.client.put(reverse('debtor-transaction-detail', args=(4, 4)), self.new_transaction)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data, self.deleted_debtor)

    def test_delete_transaction(self):
        response = self.client.delete(reverse('debtor-transaction-detail', args=(1, 1)))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        response = self.client.get(reverse('debtor-transaction-list', args=(1,)), {'page': 1, 'size': 2})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, self.transaction_list_delete)


class RegisterTestCase(ApiUserTestClient):

    def setUp(self):
        super().setUp()

        self.new_user = [{
            "username": "test3",
            "first_name": "test",
            "last_name": "test",
            "email": "test3@example.com",
            "password1": "SlojniyParol123",
            "password2": "SlojniyParol123",
            "currency": "dollars"
        },{
            "username": "test4",
            "first_name": "test",
            "last_name": "test",
            "email": "tes4@example.com",
            "password1": "SlojniyParol123",
            "password2": "SlojniyParol123",
            "currency": "руб"
        }]

        self.different_password = {
            "username": "test3",
            "first_name": "test",
            "last_name": "test",
            "email": "test@example.com",
            "password1": "SlojniyParol123",
            "password2": "SlojniyParol1234",
            "currency": "dollars"
        }

        self.weak_password = {
            "username": "test3",
            "first_name": "test",
            "last_name": "test",
            "email": "test@example.com",
            "password1": "123",
            "password2": "123",
            "currency": "dollars"
        }

        self.dublicate_email = {
            "username": "test3",
            "first_name": "test",
            "last_name": "test",
            "email": "test@test.com",
            "password1": "123",
            "password2": "123",
            "currency": "dollars"
        }

        self.dublicate_email_error = {
                                        "email": [
                                            "user with this email already exists."
                                        ]
                                    }

        self.different_password_error = {
            "non_field_errors": [
                "Passwords do not match"
            ]
        }

        self.weak_password_error = {
            "non_field_errors": [
                "Unsuccessful attempt to register: ["
                "'This password is too short. It must contain at least 8 characters.',"
                " 'This password is too common.', 'This password is entirely numeric.']"
            ]
        }

    def find_link(self, message):
        regex = 'http:\/\/testserver\/api\/v1\/register\/activate\/' \
                '(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
        register_link = re.findall(regex, message)
        return register_link

    def test_allowed_methods(self):
        response = self.client.get(reverse('register-list'))
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        response = self.client.put(reverse('register-list'))
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        response = self.client.patch(reverse('register-list'))
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        response = self.client.delete(reverse('register-list'))
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_different_password(self):
        response = self.client.post(reverse('register-list'), self.different_password)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, self.different_password_error)

    def test_weak_password(self):
        response = self.client.post(reverse('register-list'), self.weak_password)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, self.weak_password_error)

    def test_email_exist(self):
        response = self.client.post(reverse('register-list'), self.dublicate_email)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, self.dublicate_email_error)

    def test_register(self):
        response = self.client.post(reverse('register-list'), self.new_user[0])
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        message = mail.outbox[0].body
        activation_link = self.find_link(message)
        self.assertEqual(len(activation_link), 1)
        response = self.client.get(activation_link[0])
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user = User.objects.last()
        currency = CurrencyOwner.objects.get(owner=user).currency.name
        self.assertEqual(currency, self.new_user[0]['currency'])

        response = self.client.post(reverse('register-list'), self.new_user[1])
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.last()
        currency = CurrencyOwner.objects.get(owner=user).currency.name
        self.assertEqual(currency, self.new_user[1]['currency'])