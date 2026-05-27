from django.urls import path
from . import views

app_name = 'whatsapp'

urlpatterns = [
    path('webhook/', views.WebhookView.as_view(), name='webhook'),

    # Inbox
    path('inbox/', views.InboxView.as_view(), name='inbox'),
    path('api/inbox/updates/', views.InboxUpdatesAPIView.as_view(), name='inbox_updates_api'),

    # Conversation
    path('conversacion/<int:pk>/', views.ConversacionDetailView.as_view(), name='conversacion'),
    path('conversacion/<int:pk>/mensajes/', views.ConversacionMessagesAPIView.as_view(), name='conversacion_messages_api'),
    path('conversacion/iniciar/<int:lead_pk>/', views.IniciarConversacionView.as_view(), name='iniciar_conversacion'),
    path('conversacion/iniciar-cliente/<int:cliente_pk>/', views.IniciarConversacionClienteView.as_view(), name='iniciar_conversacion_cliente'),

    # Bot
    path('bot/', views.BotReglaListView.as_view(), name='bot_list'),
    path('bot/nueva/', views.BotReglaCreateView.as_view(), name='bot_create'),
    path('bot/<int:pk>/editar/', views.BotReglaUpdateView.as_view(), name='bot_update'),
    path('bot/<int:pk>/toggle/', views.BotReglaToggleView.as_view(), name='bot_toggle'),
    path('bot/<int:pk>/eliminar/', views.BotReglaDeleteView.as_view(), name='bot_delete'),

    # Configuration (supervisor+)
    path('configuracion/', views.WhatsAppConfigView.as_view(), name='config'),
    path('configuracion/qr/', views.QRCodeView.as_view(), name='qr_code'),
    path('configuracion/estado/', views.ConnectionStatusView.as_view(), name='connection_status'),

    # Templates
    path('plantillas/', views.PlantillaListView.as_view(), name='plantilla_list'),
    path('plantillas/nueva/', views.PlantillaCreateView.as_view(), name='plantilla_create'),
    path('plantillas/<int:pk>/editar/', views.PlantillaUpdateView.as_view(), name='plantilla_update'),
    path('plantillas/<int:pk>/eliminar/', views.PlantillaDeleteView.as_view(), name='plantilla_delete'),
    path('plantillas/<int:pk>/preview/', views.PlantillaPreviewView.as_view(), name='plantilla_preview'),
]
