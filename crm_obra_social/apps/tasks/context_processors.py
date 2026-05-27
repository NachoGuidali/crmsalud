def pending_tasks_count(request):
    if not request.user.is_authenticated:
        return {'pending_tasks_count': 0}
    from .models import Tarea
    from django.utils import timezone
    hoy = timezone.localdate()
    qs = Tarea.objects.filter(status=Tarea.STATUS_PENDIENTE, fecha_programada__date=hoy)
    if not request.user.can_see_all_leads:
        qs = qs.filter(agente=request.user)
    return {'pending_tasks_count': qs.count()}
