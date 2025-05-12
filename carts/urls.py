from django.urls import path
from .views import add_to_cart, list_cart_items

urlpatterns = [
    path('add/', add_to_cart, name='add_to_cart'),
    path('list/', list_cart_items, name='list_cart_items'),
]
