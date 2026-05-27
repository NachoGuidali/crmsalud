import json
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import ListView

from .models import ChatBot, ChatBotFlow


class BotListView(LoginRequiredMixin, ListView):
    model = ChatBot
    template_name = 'chatbot/bot_list.html'
    context_object_name = 'bots'

    def get_queryset(self):
        return ChatBot.objects.select_related('creado_por').order_by('-created_at')


class BotCreateView(LoginRequiredMixin, View):
    template_name = 'chatbot/bot_form.html'

    def get(self, request):
        return render(request, self.template_name, {'action': 'crear', 'nombre': '', 'descripcion': ''})

    def post(self, request):
        nombre = request.POST.get('nombre', '').strip()
        descripcion = request.POST.get('descripcion', '').strip()
        if not nombre:
            messages.error(request, 'El nombre es requerido.')
            return render(request, self.template_name, {
                'action': 'crear',
                'nombre': nombre,
                'descripcion': descripcion,
            })
        bot = ChatBot.objects.create(
            nombre=nombre,
            descripcion=descripcion,
            creado_por=request.user,
        )
        ChatBotFlow.objects.create(bot=bot)
        messages.success(request, f'Bot "{bot.nombre}" creado.')
        return redirect('chatbot:builder', pk=bot.pk)


class BotUpdateView(LoginRequiredMixin, View):
    template_name = 'chatbot/bot_form.html'

    def get(self, request, pk):
        bot = get_object_or_404(ChatBot, pk=pk)
        return render(request, self.template_name, {'action': 'editar', 'bot': bot})

    def post(self, request, pk):
        bot = get_object_or_404(ChatBot, pk=pk)
        nombre = request.POST.get('nombre', '').strip()
        descripcion = request.POST.get('descripcion', '').strip()
        activo = request.POST.get('activo') == 'on'
        if not nombre:
            messages.error(request, 'El nombre es requerido.')
            return render(request, self.template_name, {'action': 'editar', 'bot': bot})
        bot.nombre = nombre
        bot.descripcion = descripcion
        bot.activo = activo
        bot.save(update_fields=['nombre', 'descripcion', 'activo', 'updated_at'])
        messages.success(request, 'Bot actualizado.')
        return redirect('chatbot:list')


class BotDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        bot = get_object_or_404(ChatBot, pk=pk)
        nombre = bot.nombre
        bot.delete()
        messages.success(request, f'Bot "{nombre}" eliminado.')
        return redirect('chatbot:list')


class BotToggleView(LoginRequiredMixin, View):
    def post(self, request, pk):
        bot = get_object_or_404(ChatBot, pk=pk)
        bot.activo = not bot.activo
        bot.save(update_fields=['activo'])
        return JsonResponse({'activo': bot.activo})


class BotBuilderView(LoginRequiredMixin, View):
    template_name = 'chatbot/bot_builder.html'

    def get(self, request, pk):
        bot = get_object_or_404(ChatBot, pk=pk)
        flow, _ = ChatBotFlow.objects.get_or_create(bot=bot)
        return render(request, self.template_name, {'bot': bot, 'flow': flow})


class BotFlowAPIView(LoginRequiredMixin, View):
    def get(self, request, pk):
        bot = get_object_or_404(ChatBot, pk=pk)
        flow, _ = ChatBotFlow.objects.get_or_create(bot=bot)
        return JsonResponse({'data': flow.drawflow_data})

    def post(self, request, pk):
        bot = get_object_or_404(ChatBot, pk=pk)
        try:
            body = json.loads(request.body)
            data = body.get('data', {})
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'JSON inválido'}, status=400)
        flow, _ = ChatBotFlow.objects.get_or_create(bot=bot)
        flow.drawflow_data = data
        flow.save(update_fields=['drawflow_data', 'updated_at'])
        return JsonResponse({'ok': True})
