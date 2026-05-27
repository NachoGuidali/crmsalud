from django.contrib import admin
from .models import ChatBot, ChatBotFlow


@admin.register(ChatBot)
class ChatBotAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'activo', 'creado_por', 'created_at']
    list_filter = ['activo']


@admin.register(ChatBotFlow)
class ChatBotFlowAdmin(admin.ModelAdmin):
    list_display = ['bot', 'updated_at']
