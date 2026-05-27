from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.files.base import ContentFile
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import DetailView

from apps.leads.models import Lead
from .forms import CotizacionForm, IntegranteFormSet
from .models import Cotizacion
from .pdf import generate_cotizacion_pdf


class CotizacionCreateView(LoginRequiredMixin, View):
    template_name = 'quotes/cotizacion_form.html'

    def _get_lead(self, request):
        lead_pk = request.GET.get('lead') or request.POST.get('lead')
        qs = Lead.objects.all()
        if not request.user.can_see_all_leads:
            qs = qs.filter(agente=request.user)
        return get_object_or_404(qs, pk=lead_pk) if lead_pk else None

    def get(self, request):
        lead = self._get_lead(request)
        form = CotizacionForm(lead=lead)
        formset = IntegranteFormSet()
        return render(request, self.template_name, {'form': form, 'formset': formset, 'lead': lead})

    def post(self, request):
        lead = self._get_lead(request)
        form = CotizacionForm(request.POST, lead=lead)
        formset = IntegranteFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            cotizacion = form.save(commit=False)
            cotizacion.creado_por = request.user
            cotizacion.save()
            formset.instance = cotizacion
            formset.save()
            messages.success(request, 'Cotización creada correctamente.')
            return redirect('quotes:detail', pk=cotizacion.pk)
        return render(request, self.template_name, {'form': form, 'formset': formset, 'lead': lead})


class CotizacionDetailView(LoginRequiredMixin, DetailView):
    model = Cotizacion
    template_name = 'quotes/cotizacion_detail.html'
    context_object_name = 'cotizacion'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['integrantes'] = self.object.integrantes.all()
        return ctx


class CotizacionPDFView(LoginRequiredMixin, View):
    def get(self, request, pk):
        cotizacion = get_object_or_404(Cotizacion, pk=pk)
        pdf_bytes = generate_cotizacion_pdf(cotizacion)
        if not cotizacion.pdf_file:
            cotizacion.pdf_file.save(f'cotizacion_{pk}.pdf', ContentFile(pdf_bytes), save=True)
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="cotizacion_{pk}.pdf"'
        return response


class CotizacionWhatsAppSendView(LoginRequiredMixin, View):
    """Send cotizacion PDF to lead via WhatsApp."""

    def post(self, request, pk):
        cotizacion = get_object_or_404(Cotizacion, pk=pk)
        lead = cotizacion.lead
        if not lead.telefono:
            messages.error(request, 'El lead no tiene teléfono registrado.')
            return redirect('quotes:detail', pk=pk)

        # Ensure PDF exists
        if not cotizacion.pdf_file:
            pdf_bytes = generate_cotizacion_pdf(cotizacion)
            cotizacion.pdf_file.save(f'cotizacion_{pk}.pdf', ContentFile(pdf_bytes), save=True)

        from django.conf import settings
        doc_url = request.build_absolute_uri(cotizacion.pdf_file.url)
        from apps.whatsapp.sender import send_media_message
        try:
            send_media_message(lead.telefono, doc_url, 'document', filename=f'Cotizacion_{pk}.pdf', caption=f'Cotización de plan {cotizacion.plan}')
            messages.success(request, 'Cotización enviada por WhatsApp.')
        except Exception as e:
            messages.error(request, f'Error al enviar: {e}')
        return redirect('quotes:detail', pk=pk)
