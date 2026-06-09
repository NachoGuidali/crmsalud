from django.urls import path
from . import views

app_name = 'users'

urlpatterns = [
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('', views.UserListView.as_view(), name='list'),
    path('nuevo/', views.UserCreateView.as_view(), name='create'),
    path('<int:pk>/editar/', views.UserUpdateView.as_view(), name='update'),
    path('perfil/', views.ProfileView.as_view(), name='profile'),
    path('heartbeat/', views.HeartbeatView.as_view(), name='heartbeat'),
    path('toggle-disponible/', views.ToggleDisponibleView.as_view(), name='toggle_disponible'),
]
