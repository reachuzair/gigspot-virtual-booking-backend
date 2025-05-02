from django.urls import path
from .views import (
    signup, 
    verify_otp, 
    resend_otp, 
    login_view, 
    logout_view, 
    forgot_password,
    change_password,
    reset_password
    )

urlpatterns = [
    path('signup/', signup, name='signup'),
    path('verify-otp/', verify_otp, name='verify_otp'),
    path('resend-otp/<str:email>/', resend_otp, name='resend_otp'),
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('forgot-password/', forgot_password, name='forgot_password'),
    path('change-password/', change_password, name='change_password'),
    path('reset-password/', reset_password, name='reset_password'),
]