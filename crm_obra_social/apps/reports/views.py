import csv
from datetime import timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from apps.leads.models import Lead
from apps.tasks.models import Tarea
from apps.whatsapp.models import Conversacion, Mensaje


class DashboardView(LoginRequiredMixin, View):
    template_name = 'reports/dashboard.html'

    def get(self, request):
        user = request.user
        hoy = timezone.localdate()
        inicio_semana = hoy - timedelta(days=hoy.weekday())

        lead_qs = Lead.objects.all()
        tarea_qs = Tarea.objects.all()
        conv_qs = Conversacion.objects.all()

        if not user.can_see_all_leads:
            lead_qs = lead_qs.filter(agente=user)
            tarea_qs = tarea_qs.filter(agente=user)
            conv_qs = conv_qs.filter(agente=user)

        # Leads by state — single aggregated query instead of N queries
        estado_counts = {
            row['estado']: row['total']
            for row in lead_qs.values('estado').annotate(total=Count('id'))
        }
        leads_por_estado = {
            estado: estado_counts.get(estado, 0)
            for estado, _ in Lead.ESTADO_CHOICES
        }

        # Tasks due today
        tareas_hoy = tarea_qs.filter(fecha_programada__date=hoy, status=Tarea.STATUS_PENDIENTE).select_related('lead')[:10]

        # Unread conversations
        conv_sin_respuesta = conv_qs.filter(mensajes_no_leidos__gt=0).count()

        # Recent activity (last 10 leads updated)
        actividad_reciente = lead_qs.order_by('-updated_at')[:10]

        # Agent ranking (supervisors/admins)
        ranking_agentes = None
        if user.can_see_all_leads:
            from apps.users.models import User
            ranking_agentes = (
                User.objects.filter(is_active=True, role__in=['agente', 'supervisor'])
                .annotate(afiliados=Count('leads_asignados', filter=Q(leads_asignados__estado=Lead.ESTADO_AFILIADO)))
                .order_by('-afiliados')[:10]
            )

        # Leads this week
        leads_semana = lead_qs.filter(created_at__date__gte=inicio_semana).count()

        ctx = {
            'leads_por_estado': leads_por_estado,
            'estado_choices': Lead.ESTADO_CHOICES,
            'tareas_hoy': tareas_hoy,
            'conv_sin_respuesta': conv_sin_respuesta,
            'actividad_reciente': actividad_reciente,
            'ranking_agentes': ranking_agentes,
            'leads_semana': leads_semana,
            'total_leads': lead_qs.count(),
        }
        return render(request, self.template_name, ctx)


class ReporteConversionView(LoginRequiredMixin, View):
    template_name = 'reports/reporte_conversion.html'

    def get(self, request):
        lead_qs = Lead.objects.all()
        if not request.user.can_see_all_leads:
            lead_qs = lead_qs.filter(agente=request.user)

        estado_counts = {
            row['estado']: row['total']
            for row in lead_qs.values('estado').annotate(total=Count('id'))
        }
        funnel = [
            {'estado': estado, 'label': label, 'count': estado_counts.get(estado, 0)}
            for estado, label in Lead.ESTADO_CHOICES
        ]

        por_origen = lead_qs.values('origen').annotate(total=Count('id')).order_by('-total')
        por_agente = lead_qs.values('agente__first_name', 'agente__last_name').annotate(total=Count('id')).order_by('-total')

        ctx = {'funnel': funnel, 'por_origen': por_origen, 'por_agente': por_agente}
        return render(request, self.template_name, ctx)


class ReporteMensajesView(LoginRequiredMixin, View):
    template_name = 'reports/reporte_mensajes.html'

    def get(self, request):
        desde = request.GET.get('desde')
        hasta = request.GET.get('hasta')
        msg_qs = Mensaje.objects.all()
        if desde:
            msg_qs = msg_qs.filter(timestamp__date__gte=desde)
        if hasta:
            msg_qs = msg_qs.filter(timestamp__date__lte=hasta)

        ctx = {
            'enviados': msg_qs.filter(direccion=Mensaje.DIR_SALIENTE).count(),
            'recibidos': msg_qs.filter(direccion=Mensaje.DIR_ENTRANTE).count(),
            'desde': desde,
            'hasta': hasta,
        }
        return render(request, self.template_name, ctx)


class ReporteExportCSVView(LoginRequiredMixin, View):
    def get(self, request):
        lead_qs = Lead.objects.select_related('agente', 'plan_interes').all()
        if not request.user.can_see_all_leads:
            lead_qs = lead_qs.filter(agente=request.user)

        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="reporte_leads.csv"'
        response.write('﻿')
        writer = csv.writer(response)
        writer.writerow(['Estado', 'Cantidad'])
        for estado, label in Lead.ESTADO_CHOICES:
            writer.writerow([label, lead_qs.filter(estado=estado).count()])
        return response


def error_404(request, exception=None):
    return render(request, 'errors/404.html', status=404)


def error_500(request):
    return render(request, 'errors/500.html', status=500)
