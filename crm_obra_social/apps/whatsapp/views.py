import json
import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.views.decorators.csrf import csrf_exempt

from apps.users.models import User
from .models import Conversacion, Mensaje, PlantillaHSM, ConfiguracionWhatsApp
from .tasks import process_incoming_message, send_whatsapp_message_task
from .webhook import parse_incoming_webhook, verify_webhook_token

logger = logging.getLogger('apps.whatsapp')


def _auto_contactado(conv):
    """Change lead status from NUEVO → CONTACTADO when a message is sent/received."""
    from apps.leads.models import Lead, HistorialEstado
    lead = conv.lead
    if lead and lead.estado == Lead.ESTADO_NUEVO:
        Lead.objects.filter(pk=lead.pk).update(estado=Lead.ESTADO_CONTACTADO)
        HistorialEstado.objects.create(
            lead=lead,
            estado_anterior=Lead.ESTADO_NUEVO,
            estado_nuevo=Lead.ESTADO_CONTACTADO,
            nota='Cambio automático al iniciar conversación WhatsApp.',
        )


@method_decorator(csrf_exempt, name='dispatch')
class WebhookView(View):
    def get(self, request):
        """Evolution API webhook verification (not used by Evolution API, kept for compatibility)."""
        return HttpResponse('OK', status=200)

    def post(self, request):
        """Receive and queue incoming messages from Evolution API."""
        token = request.headers.get('apikey', '')
        configured_token = ConfiguracionWhatsApp.get_setting('webhook_token')
        if not verify_webhook_token(token, configured_token):
            logger.warning('Invalid webhook token — request rejected')
            return HttpResponse('Forbidden', status=403)
        try:
            payload = json.loads(request.body)
            logger.debug('Webhook received: %s', json.dumps(payload)[:500])
            messages_data = parse_incoming_webhook(payload)
            for msg_data in messages_data:
                process_incoming_message.delay(msg_data)
        except Exception as e:
            logger.exception('Webhook processing error: %s', e)
        return HttpResponse('OK', status=200)


class InboxView(LoginRequiredMixin, View):
    template_name = 'whatsapp/inbox.html'

    def _get_convs_qs(self, request):
        from django.db.models import Q
        qs = Conversacion.objects.select_related('lead', 'agente').order_by('-ultimo_mensaje_at', '-pk')
        if not request.user.can_see_all_leads:
            qs = qs.filter(Q(agente=request.user) | Q(lead__agente=request.user)).distinct()
        return qs

    def get(self, request):
        from django.db.models import Q
        from apps.leads.models import Lead

        qs = self._get_convs_qs(request)

        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(nombre_contacto__icontains=q) | Q(telefono__icontains=q) |
                Q(lead__nombre_completo__icontains=q)
            )

        estado = request.GET.get('estado', '').strip()
        if estado:
            qs = qs.filter(lead__estado=estado)

        solo_no_leidos = request.GET.get('no_leidos', '').strip()
        if solo_no_leidos:
            qs = qs.filter(mensajes_no_leidos__gt=0)

        conversaciones = list(qs[:100])
        unread_total = self._get_convs_qs(request).filter(mensajes_no_leidos__gt=0).count()

        conv_pk_str = request.GET.get('conv', '').strip()
        selected_conv = None
        mensajes = []
        plantillas = []
        agents = None
        last_msg_id = 0

        if conv_pk_str:
            try:
                selected_conv = self._get_convs_qs(request).get(pk=int(conv_pk_str))
                Conversacion.objects.filter(pk=selected_conv.pk).update(mensajes_no_leidos=0)
                msgs_qs = selected_conv.mensajes.order_by('timestamp')
                total = msgs_qs.count()
                mensajes = list(msgs_qs[max(0, total - 60):])
                plantillas = PlantillaHSM.objects.filter(activa=True)
                agents = User.objects.filter(is_active=True) if request.user.can_see_all_leads else None
                last_msg = selected_conv.mensajes.order_by('timestamp').last()
                last_msg_id = last_msg.pk if last_msg else 0
            except (Conversacion.DoesNotExist, ValueError, TypeError):
                selected_conv = None

        return render(request, self.template_name, {
            'conversaciones': conversaciones,
            'unread_total': unread_total,
            'q': q,
            'estado': estado,
            'solo_no_leidos': solo_no_leidos,
            'selected_conv': selected_conv,
            'mensajes': mensajes,
            'plantillas': plantillas,
            'agents': agents,
            'last_msg_id': last_msg_id,
            'estado_choices': Lead.ESTADO_CHOICES,
        })

    def post(self, request):
        from django.urls import reverse
        conv_pk = request.POST.get('conv_pk', '').strip()
        if not conv_pk:
            return redirect('whatsapp:inbox')

        conv = get_object_or_404(self._get_convs_qs(request), pk=conv_pk)
        action = request.POST.get('action', '')

        if action == 'send_text':
            body = request.POST.get('body', '').strip()
            if not body:
                messages.error(request, 'El mensaje no puede estar vacío.')
            else:
                msg = Mensaje.objects.create(
                    conversacion=conv, lead=conv.lead,
                    direccion=Mensaje.DIR_SALIENTE, tipo=Mensaje.TIPO_TEXTO,
                    contenido=body, status=Mensaje.STATUS_PENDIENTE,
                    enviado_por=request.user, timestamp=timezone.now(),
                )
                send_whatsapp_message_task.delay(msg.pk)
                Conversacion.objects.filter(pk=conv.pk).update(ultimo_mensaje_at=timezone.now())
                _auto_contactado(conv)

        elif action == 'send_template':
            from .sender import send_text_message
            plantilla_id = request.POST.get('plantilla_id')
            if not plantilla_id:
                messages.error(request, 'Seleccioná una plantilla.')
            else:
                plantilla = get_object_or_404(PlantillaHSM, pk=plantilla_id)
                variables_vals = [request.POST.get(f'var_{i + 1}', '') for i in range(len(plantilla.variables or []))]
                text = plantilla.preview(variables_vals if any(variables_vals) else None)
                try:
                    result = send_text_message(conv.telefono, text)
                    wam_id = result.get('id', '')
                    Mensaje.objects.create(
                        conversacion=conv, lead=conv.lead,
                        direccion=Mensaje.DIR_SALIENTE, tipo=Mensaje.TIPO_PLANTILLA,
                        contenido=text, whatsapp_message_id=wam_id,
                        status=Mensaje.STATUS_ENVIADO, enviado_por=request.user, timestamp=timezone.now(),
                    )
                    Conversacion.objects.filter(pk=conv.pk).update(ultimo_mensaje_at=timezone.now())
                    _auto_contactado(conv)
                    messages.success(request, 'Plantilla enviada.')
                except Exception as e:
                    messages.error(request, f'Error al enviar la plantilla: {e}')

        elif action == 'send_interactive':
            body_text = request.POST.get('interactive_body', '').strip()
            btn_titles = [t.strip() for t in request.POST.getlist('btn_title') if t.strip()]
            if not body_text or not btn_titles:
                messages.error(request, 'El cuerpo y al menos un botón son requeridos.')
            else:
                buttons = [{'id': f'btn_{i}', 'title': title} for i, title in enumerate(btn_titles[:3])]
                from .sender import send_interactive_message
                try:
                    result = send_interactive_message(
                        conv.telefono, body_text, buttons,
                        request.POST.get('interactive_header', '').strip(),
                        request.POST.get('interactive_footer', '').strip(),
                    )
                    wam_id = result.get('id', '')
                    Mensaje.objects.create(
                        conversacion=conv, lead=conv.lead,
                        direccion=Mensaje.DIR_SALIENTE, tipo=Mensaje.TIPO_INTERACTIVO,
                        contenido=body_text + '\n' + ' | '.join(f'[{b["title"]}]' for b in buttons),
                        whatsapp_message_id=wam_id, status=Mensaje.STATUS_ENVIADO,
                        enviado_por=request.user, timestamp=timezone.now(),
                    )
                    Conversacion.objects.filter(pk=conv.pk).update(ultimo_mensaje_at=timezone.now())
                    messages.success(request, 'Mensaje con botones enviado.')
                except Exception as e:
                    messages.error(request, f'Error al enviar: {e}')

        elif action == 'assign_agent' and request.user.can_see_all_leads:
            agente_id = request.POST.get('agente_id')
            conv.agente_id = agente_id or None
            conv.save(update_fields=['agente_id'])
            messages.success(request, 'Agente asignado.')

        params = [f'conv={conv.pk}']
        q = request.POST.get('_q', '')
        est = request.POST.get('_estado', '')
        no_leidos = request.POST.get('_no_leidos', '')
        if q: params.append(f'q={q}')
        if est: params.append(f'estado={est}')
        if no_leidos: params.append('no_leidos=1')
        from django.urls import reverse
        return redirect(f"{reverse('whatsapp:inbox')}?{'&'.join(params)}")


class ConversacionDetailView(LoginRequiredMixin, View):
    template_name = 'whatsapp/conversacion.html'

    def _get_conv(self, request, pk):
        from django.db.models import Q
        qs = Conversacion.objects.select_related('lead', 'agente')
        if not request.user.can_see_all_leads:
            qs = qs.filter(Q(agente=request.user) | Q(lead__agente=request.user))
        return get_object_or_404(qs.distinct(), pk=pk)

    def get(self, request, pk):
        conv = self._get_conv(request, pk)
        Conversacion.objects.filter(pk=pk).update(mensajes_no_leidos=0)
        mensajes_qs = conv.mensajes.order_by('timestamp')
        paginator = Paginator(mensajes_qs, 50)
        page = paginator.get_page(request.GET.get('page', paginator.num_pages))
        plantillas = PlantillaHSM.objects.filter(activa=True)
        agents = User.objects.filter(is_active=True) if request.user.can_see_all_leads else None
        last_msg = conv.mensajes.order_by('timestamp').last()
        return render(request, self.template_name, {
            'conv': conv,
            'mensajes': page,
            'plantillas': plantillas,
            'agents': agents,
            'last_msg_id': last_msg.pk if last_msg else 0,
        })

    def post(self, request, pk):
        conv = self._get_conv(request, pk)
        action = request.POST.get('action')

        if action == 'send_text':
            body = request.POST.get('body', '').strip()
            if not body:
                messages.error(request, 'El mensaje no puede estar vacío.')
                return redirect('whatsapp:conversacion', pk=pk)
            msg = Mensaje.objects.create(
                conversacion=conv, lead=conv.lead,
                direccion=Mensaje.DIR_SALIENTE, tipo=Mensaje.TIPO_TEXTO,
                contenido=body, status=Mensaje.STATUS_PENDIENTE,
                enviado_por=request.user, timestamp=timezone.now(),
            )
            send_whatsapp_message_task.delay(msg.pk)
            Conversacion.objects.filter(pk=pk).update(ultimo_mensaje_at=timezone.now())
            _auto_contactado(conv)

        elif action == 'send_template':
            from .sender import send_text_message
            plantilla_id = request.POST.get('plantilla_id')
            if not plantilla_id:
                messages.error(request, 'Seleccioná una plantilla.')
                return redirect('whatsapp:conversacion', pk=pk)
            plantilla = get_object_or_404(PlantillaHSM, pk=plantilla_id)
            variables_vals = [
                request.POST.get(f'var_{i + 1}', '')
                for i in range(len(plantilla.variables or []))
            ]
            text = plantilla.preview(variables_vals if any(variables_vals) else None)
            try:
                result = send_text_message(conv.telefono, text)
                wam_id = result.get('id', '')
                Mensaje.objects.create(
                    conversacion=conv, lead=conv.lead,
                    direccion=Mensaje.DIR_SALIENTE, tipo=Mensaje.TIPO_PLANTILLA,
                    contenido=text, whatsapp_message_id=wam_id,
                    status=Mensaje.STATUS_ENVIADO, enviado_por=request.user, timestamp=timezone.now(),
                )
                Conversacion.objects.filter(pk=pk).update(ultimo_mensaje_at=timezone.now())
                _auto_contactado(conv)
                messages.success(request, 'Plantilla enviada.')
            except Exception as e:
                messages.error(request, f'Error al enviar la plantilla: {e}')

        elif action == 'send_interactive':
            body_text = request.POST.get('interactive_body', '').strip()
            header_text = request.POST.get('interactive_header', '').strip()
            footer_text = request.POST.get('interactive_footer', '').strip()
            btn_titles = [t.strip() for t in request.POST.getlist('btn_title') if t.strip()]
            if not body_text or not btn_titles:
                messages.error(request, 'El cuerpo y al menos un botón son requeridos.')
                return redirect('whatsapp:conversacion', pk=pk)
            buttons = [{'id': f'btn_{i}', 'title': title} for i, title in enumerate(btn_titles[:3])]
            from .sender import send_interactive_message
            try:
                result = send_interactive_message(conv.telefono, body_text, buttons, header_text, footer_text)
                wam_id = result.get('id', '')
                btn_display = ' | '.join(f'[{b["title"]}]' for b in buttons)
                Mensaje.objects.create(
                    conversacion=conv, lead=conv.lead,
                    direccion=Mensaje.DIR_SALIENTE, tipo=Mensaje.TIPO_INTERACTIVO,
                    contenido=body_text + '\n' + btn_display,
                    whatsapp_message_id=wam_id, status=Mensaje.STATUS_ENVIADO,
                    enviado_por=request.user, timestamp=timezone.now(),
                )
                Conversacion.objects.filter(pk=pk).update(ultimo_mensaje_at=timezone.now())
                messages.success(request, 'Mensaje con botones enviado.')
            except Exception as e:
                messages.error(request, f'Error al enviar mensaje interactivo: {e}')

        elif action == 'assign_agent' and request.user.can_see_all_leads:
            agente_id = request.POST.get('agente_id')
            conv.agente_id = agente_id or None
            conv.save(update_fields=['agente_id'])
            messages.success(request, 'Agente asignado.')

        return redirect('whatsapp:conversacion', pk=pk)


class ConversacionMessagesAPIView(LoginRequiredMixin, View):
    """JSON polling endpoint: returns messages newer than since_id."""

    def get(self, request, pk):
        from django.db.models import Q
        qs = Conversacion.objects.all()
        if not request.user.can_see_all_leads:
            qs = qs.filter(Q(agente=request.user) | Q(lead__agente=request.user)).distinct()
        conv = get_object_or_404(qs, pk=pk)
        since_id = int(request.GET.get('since_id', 0))
        nuevos = conv.mensajes.filter(pk__gt=since_id).order_by('timestamp')
        if nuevos.exists():
            Conversacion.objects.filter(pk=pk).update(mensajes_no_leidos=0)
        data = []
        for msg in nuevos:
            data.append({
                'id': msg.pk,
                'direccion': msg.direccion,
                'tipo': msg.tipo,
                'contenido': msg.contenido,
                'media_url': msg.media_url,
                'status': msg.status,
                'timestamp': msg.timestamp.strftime('%d/%m %H:%M'),
            })
        return JsonResponse({'mensajes': data})


class InboxUpdatesAPIView(LoginRequiredMixin, View):
    """JSON polling endpoint: returns unread conversation counts for the inbox."""

    def get(self, request):
        qs = Conversacion.objects.filter(mensajes_no_leidos__gt=0)
        if not request.user.can_see_all_leads:
            qs = qs.filter(agente=request.user)
        unread_total = qs.count()
        conv_ids = list(qs.values_list('id', flat=True))
        return JsonResponse({'unread_total': unread_total, 'conv_ids': conv_ids})


class BotReglaListView(LoginRequiredMixin, View):
    template_name = 'whatsapp/bot_list.html'

    def get(self, request):
        from .models import BotRespuesta
        reglas = BotRespuesta.objects.all()
        plantillas = PlantillaHSM.objects.filter(activa=True)
        return render(request, self.template_name, {'reglas': reglas, 'plantillas': plantillas})


class BotReglaToggleView(LoginRequiredMixin, View):
    def post(self, request, pk):
        from .models import BotRespuesta
        regla = get_object_or_404(BotRespuesta, pk=pk)
        regla.activa = not regla.activa
        regla.save(update_fields=['activa'])
        return JsonResponse({'activa': regla.activa})


class BotReglaCreateView(LoginRequiredMixin, View):
    template_name = 'whatsapp/bot_form.html'

    def get(self, request):
        from .models import BotRespuesta
        from apps.leads.models import Lead
        return render(request, self.template_name, {
            'plantillas': PlantillaHSM.objects.filter(activa=True),
            'trigger_choices': BotRespuesta.TRIGGER_CHOICES,
            'respuesta_choices': BotRespuesta.RESPUESTA_CHOICES,
            'estado_choices': Lead.ESTADO_CHOICES,
            'prioridad_choices': Lead.PRIORIDAD_CHOICES,
        })

    def post(self, request):
        from .models import BotRespuesta
        from apps.leads.models import Lead
        err, regla = _save_bot_regla(request.POST, None)
        if err:
            messages.error(request, err)
            return render(request, self.template_name, {
                'plantillas': PlantillaHSM.objects.filter(activa=True),
                'trigger_choices': BotRespuesta.TRIGGER_CHOICES,
                'respuesta_choices': BotRespuesta.RESPUESTA_CHOICES,
                'estado_choices': Lead.ESTADO_CHOICES,
                'prioridad_choices': Lead.PRIORIDAD_CHOICES,
                'data': request.POST,
            })
        messages.success(request, 'Regla de bot creada.')
        return redirect('whatsapp:bot_list')


class BotReglaUpdateView(LoginRequiredMixin, View):
    template_name = 'whatsapp/bot_form.html'

    def get(self, request, pk):
        from .models import BotRespuesta
        from apps.leads.models import Lead
        regla = get_object_or_404(BotRespuesta, pk=pk)
        return render(request, self.template_name, {
            'regla': regla,
            'plantillas': PlantillaHSM.objects.filter(activa=True),
            'trigger_choices': BotRespuesta.TRIGGER_CHOICES,
            'respuesta_choices': BotRespuesta.RESPUESTA_CHOICES,
            'estado_choices': Lead.ESTADO_CHOICES,
            'prioridad_choices': Lead.PRIORIDAD_CHOICES,
        })

    def post(self, request, pk):
        from .models import BotRespuesta
        regla = get_object_or_404(BotRespuesta, pk=pk)
        err, regla = _save_bot_regla(request.POST, regla)
        if err:
            messages.error(request, err)
            return redirect('whatsapp:bot_update', pk=pk)
        messages.success(request, 'Regla actualizada.')
        return redirect('whatsapp:bot_list')


class BotReglaDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        from .models import BotRespuesta
        regla = get_object_or_404(BotRespuesta, pk=pk)
        regla.delete()
        messages.success(request, 'Regla eliminada.')
        return redirect('whatsapp:bot_list')


def _save_bot_regla(data, instance):
    """Returns (error_string|None, instance)."""
    from .models import BotRespuesta
    import json as _json
    nombre = data.get('nombre', '').strip()
    if not nombre:
        return 'El nombre es requerido.', None
    trigger = data.get('trigger_tipo', '')
    if trigger not in dict(BotRespuesta.TRIGGER_CHOICES):
        return 'Disparador inválido.', None

    if instance is None:
        instance = BotRespuesta()

    instance.nombre = nombre
    instance.activa = data.get('activa') == 'on'
    instance.orden = int(data.get('orden', 0) or 0)
    instance.trigger_tipo = trigger

    raw_kw = data.get('palabras_clave_raw', '').strip()
    instance.palabras_clave = [k.strip() for k in raw_kw.splitlines() if k.strip()] if raw_kw else []

    instance.respuesta_tipo = data.get('respuesta_tipo', BotRespuesta.RESPUESTA_TEXTO)
    instance.respuesta_texto = data.get('respuesta_texto', '').strip()

    plantilla_id = data.get('respuesta_plantilla')
    instance.respuesta_plantilla = PlantillaHSM.objects.filter(pk=plantilla_id).first() if plantilla_id else None

    instance.respuesta_interactivo_body = data.get('respuesta_interactivo_body', '').strip()
    raw_btns = data.get('respuesta_interactivo_botones', '[]').strip()
    try:
        instance.respuesta_interactivo_botones = _json.loads(raw_btns) if raw_btns else []
    except _json.JSONDecodeError:
        instance.respuesta_interactivo_botones = []

    instance.accion_estado = data.get('accion_estado', '')
    instance.accion_prioridad = data.get('accion_prioridad', '')
    instance.solo_si_sin_agente = data.get('solo_si_sin_agente') == 'on'
    instance.solo_primera_vez = data.get('solo_primera_vez') == 'on'
    instance.save()
    return None, instance


class PlantillaListView(LoginRequiredMixin, ListView):
    model = PlantillaHSM
    template_name = 'whatsapp/plantilla_list.html'
    context_object_name = 'plantillas'
    paginate_by = 25


class PlantillaCreateView(LoginRequiredMixin, CreateView):
    model = PlantillaHSM
    template_name = 'whatsapp/plantilla_form.html'
    fields = ('nombre', 'idioma', 'cuerpo', 'variables',
              'header_tipo', 'header_contenido', 'footer', 'botones', 'activa')
    success_url = reverse_lazy('whatsapp:plantilla_list')

    def form_valid(self, form):
        messages.success(self.request, 'Plantilla creada correctamente.')
        return super().form_valid(form)


class PlantillaUpdateView(LoginRequiredMixin, UpdateView):
    model = PlantillaHSM
    template_name = 'whatsapp/plantilla_form.html'
    fields = ('nombre', 'idioma', 'cuerpo', 'variables',
              'header_tipo', 'header_contenido', 'footer', 'botones', 'activa')
    success_url = reverse_lazy('whatsapp:plantilla_list')

    def form_valid(self, form):
        messages.success(self.request, 'Plantilla actualizada.')
        return super().form_valid(form)


class PlantillaDeleteView(LoginRequiredMixin, DeleteView):
    model = PlantillaHSM
    template_name = 'whatsapp/plantilla_confirm_delete.html'
    success_url = reverse_lazy('whatsapp:plantilla_list')


class PlantillaPreviewView(LoginRequiredMixin, View):
    """AJAX: preview a template with given variable values."""

    def post(self, request, pk):
        plantilla = get_object_or_404(PlantillaHSM, pk=pk)
        data = json.loads(request.body)
        valores = data.get('valores', [])
        return JsonResponse({'preview': plantilla.preview(valores)})


class IniciarConversacionClienteView(LoginRequiredMixin, View):
    """Find or create a Conversacion for a Cliente and redirect to the inbox."""

    def post(self, request, cliente_pk):
        from apps.clientes.models import Cliente
        from django.urls import reverse
        cliente = get_object_or_404(Cliente, pk=cliente_pk)

        if not cliente.telefono or not cliente.telefono.startswith('+'):
            messages.error(request, 'El cliente no tiene un número válido en formato internacional (+...).')
            return redirect('clientes:detail', pk=cliente_pk)

        conv, created = Conversacion.objects.get_or_create(
            telefono=cliente.telefono,
            defaults={'nombre_contacto': cliente.nombre_completo, 'agente': cliente.agente},
        )
        if not created:
            fields = []
            if not conv.nombre_contacto:
                conv.nombre_contacto = cliente.nombre_completo
                fields.append('nombre_contacto')
            if not conv.agente_id and cliente.agente_id:
                conv.agente_id = cliente.agente_id
                fields.append('agente')
            if fields:
                conv.save(update_fields=fields)

        if created:
            messages.success(request, f'Conversación iniciada con {cliente.nombre_completo}.')
        return redirect(f"{reverse('whatsapp:inbox')}?conv={conv.pk}")


class IniciarConversacionView(LoginRequiredMixin, View):
    """Create a Conversacion for a lead and redirect to the chat."""

    def post(self, request, lead_pk):
        from apps.leads.models import Lead
        lead = get_object_or_404(Lead, pk=lead_pk)

        if not lead.telefono or not lead.telefono.startswith('+'):
            messages.error(request, 'El lead no tiene un número válido en formato internacional (+...).')
            return redirect('leads:detail', pk=lead_pk)

        conv, created = Conversacion.objects.get_or_create(
            telefono=lead.telefono,
            defaults={
                'lead': lead,
                'nombre_contacto': lead.nombre_completo,
                'agente': lead.agente,
            }
        )
        if not created:
            update_fields = []
            if conv.lead_id is None:
                conv.lead = lead; update_fields.append('lead')
            conv.nombre_contacto = conv.nombre_contacto or lead.nombre_completo
            update_fields.append('nombre_contacto')
            if not conv.agente_id and lead.agente_id:
                conv.agente_id = lead.agente_id; update_fields.append('agente')
            conv.save(update_fields=update_fields)

        if created:
            messages.success(request, f'Conversación creada con {lead.nombre_completo}.')
        else:
            messages.info(request, 'Ya existe una conversación con este contacto.')

        return redirect('whatsapp:conversacion', pk=conv.pk)


class WhatsAppConfigView(LoginRequiredMixin, View):
    """Supervisor/Superadmin view to configure Evolution API credentials."""
    template_name = 'whatsapp/config.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.can_see_all_leads:
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden('Solo supervisores y superadministradores pueden acceder a esta sección.')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        try:
            config = ConfiguracionWhatsApp.objects.get(pk=1)
        except ConfiguracionWhatsApp.DoesNotExist:
            config = ConfiguracionWhatsApp()
        from .sender import get_connection_state
        try:
            connection_state = get_connection_state()
        except Exception:
            connection_state = 'error'
        return render(request, self.template_name, {
            'config': config,
            'connection_state': connection_state,
        })

    def post(self, request):
        try:
            config = ConfiguracionWhatsApp.objects.get(pk=1)
        except ConfiguracionWhatsApp.DoesNotExist:
            config = ConfiguracionWhatsApp()

        config.evolution_api_url = request.POST.get('evolution_api_url', '').strip()
        config.evolution_api_key = request.POST.get('evolution_api_key', '').strip()
        config.evolution_instance_name = request.POST.get('evolution_instance_name', '').strip() or 'crm-supreg'
        config.webhook_token = request.POST.get('webhook_token', '').strip()
        config.save()
        messages.success(request, 'Configuración de WhatsApp guardada correctamente.')
        return redirect('whatsapp:config')


class QRCodeView(LoginRequiredMixin, View):
    """AJAX: get QR code from Evolution API for WhatsApp connection."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.can_see_all_leads:
            return JsonResponse({'error': 'Sin permisos'}, status=403)
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        from .sender import get_qr_code, get_connection_state, ensure_instance_exists
        try:
            ensure_instance_exists()
            state = get_connection_state()
            if state == 'open':
                return JsonResponse({'connected': True, 'qr_base64': None})
            qr = get_qr_code()
            return JsonResponse({'connected': False, 'qr_base64': qr})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


class ConnectionStatusView(LoginRequiredMixin, View):
    """AJAX: check Evolution API instance connection state."""

    def get(self, request):
        from .sender import get_connection_state
        try:
            state = get_connection_state()
            return JsonResponse({'state': state, 'connected': state == 'open'})
        except Exception as e:
            return JsonResponse({'state': 'error', 'connected': False, 'detail': str(e)})
