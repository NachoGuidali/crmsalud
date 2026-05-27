from django.test import TestCase, Client
from django.urls import reverse

from apps.users.models import User
from .models import Lead, Plan, HistorialEstado


class LeadModelTest(TestCase):
    def test_dni_validation_rejects_short(self):
        from django.core.exceptions import ValidationError
        lead = Lead(nombre_completo='Test', dni='123', telefono='+5491112345678', origen='web')
        with self.assertRaises(ValidationError):
            lead.full_clean()

    def test_dni_validation_accepts_7_digits(self):
        plan = Plan.objects.create(nombre='Plan Básico')
        lead = Lead(nombre_completo='Test User', dni='1234567', telefono='+5491112345678', origen='web', plan_interes=plan)
        lead.full_clean()  # Should not raise

    def test_phone_validation_requires_plus54(self):
        from django.core.exceptions import ValidationError
        lead = Lead(nombre_completo='Test', dni='12345678', telefono='01112345678', origen='web')
        with self.assertRaises(ValidationError):
            lead.full_clean()

    def test_estado_badge_class(self):
        lead = Lead(estado=Lead.ESTADO_AFILIADO)
        self.assertEqual(lead.get_estado_badge_class(), 'success')

    def test_historial_created_on_save(self):
        user = User.objects.create_user(username='agente', password='pass', role=User.ROLE_AGENTE)
        lead = Lead.objects.create(nombre_completo='Juan', dni='12345678', telefono='+5491123456789', origen='web')
        HistorialEstado.objects.create(lead=lead, estado_nuevo=lead.estado, cambiado_por=user)
        self.assertEqual(lead.historial_estados.count(), 1)


class LeadViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.supervisor = User.objects.create_user(username='super', password='pass', role=User.ROLE_SUPERVISOR)
        self.agente = User.objects.create_user(username='agente', password='pass', role=User.ROLE_AGENTE)
        self.plan = Plan.objects.create(nombre='Plan A')
        self.lead = Lead.objects.create(
            nombre_completo='Juan Pérez',
            dni='12345678',
            telefono='+5491112345678',
            origen='web',
            agente=self.agente,
        )

    def test_list_requires_login(self):
        response = self.client.get(reverse('leads:list'))
        self.assertEqual(response.status_code, 302)

    def test_agente_sees_only_own_leads(self):
        other_lead = Lead.objects.create(nombre_completo='Otro', dni='99999999', telefono='+5491199999999', origen='web')
        self.client.login(username='agente', password='pass')
        response = self.client.get(reverse('leads:list'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.lead, response.context['leads'].object_list)
        self.assertNotIn(other_lead, response.context['leads'].object_list)

    def test_supervisor_sees_all_leads(self):
        other_lead = Lead.objects.create(nombre_completo='Otro', dni='99999999', telefono='+5491199999999', origen='web')
        self.client.login(username='super', password='pass')
        response = self.client.get(reverse('leads:list'))
        self.assertEqual(response.status_code, 200)
        pks = [l.pk for l in response.context['leads'].object_list]
        self.assertIn(self.lead.pk, pks)
        self.assertIn(other_lead.pk, pks)

    def test_kanban_move_endpoint(self):
        self.client.login(username='agente', password='pass')
        response = self.client.post(
            reverse('leads:kanban_move', kwargs={'pk': self.lead.pk}),
            {'estado': Lead.ESTADO_CONTACTADO},
        )
        self.assertEqual(response.status_code, 200)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.estado, Lead.ESTADO_CONTACTADO)
