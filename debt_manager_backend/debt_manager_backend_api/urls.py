"""debt_manager_backend URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DebtorViewSet, TransactionViewSet, RegisterViewSet, RecaptchaAPIView
from rest_framework_nested import routers

router_v1 = DefaultRouter()
router_v1.register('debtor', DebtorViewSet, basename='debtor')
router_v1.register('register', RegisterViewSet, basename='register')
transaction_router = routers.NestedDefaultRouter(router_v1, 'debtor', lookup='debtor')
transaction_router.register('transaction', TransactionViewSet, basename='debtor-transaction')

urlpatterns = [
    path('recaptcha-v3/', RecaptchaAPIView.as_view(), name='captcha'),
    path('v1/', include(router_v1.urls)),
    path('v1/', include(transaction_router.urls)),
    path('auth/', include('oauth2_provider.urls', namespace='oauth2_provider')),
]
