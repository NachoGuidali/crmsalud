from django.urls import path
from . import views

app_name = 'leads'

urlpatterns = [
    path('', views.LeadListView.as_view(), name='list'),
    path('kanban/', views.LeadKanbanView.as_view(), name='kanban'),
    path('nuevo/', views.LeadCreateView.as_view(), name='create'),
    path('<int:pk>/', views.LeadDetailView.as_view(), name='detail'),
    path('<int:pk>/editar/', views.LeadUpdateView.as_view(), name='update'),
    path('<int:pk>/eliminar/', views.LeadDeleteView.as_view(), name='delete'),
    path('<int:pk>/estado/', views.LeadEstadoChangeView.as_view(), name='change_estado'),
    path('<int:pk>/mover/', views.LeadKanbanMoveView.as_view(), name='kanban_move'),
    path('<int:pk>/campos/', views.LeadUpdateCamposView.as_view(), name='update_campos'),
    path('<int:pk>/convertir/', views.LeadConvertirView.as_view(), name='convertir'),
    path('<int:lead_pk>/documentos/subir/', views.DocumentoUploadView.as_view(), name='documento_upload'),
    path('documentos/<int:pk>/eliminar/', views.DocumentoDeleteView.as_view(), name='documento_delete'),
    path('contactos/', views.ContactListView.as_view(), name='contact_list'),
    path('contactos/buscar/', views.ContactSearchAPIView.as_view(), name='contact_search'),
    path('importar/', views.LeadCSVImportView.as_view(), name='csv_import'),
    path('importar/template/', views.LeadImportTemplateView.as_view(), name='import_template'),
    path('exportar/', views.LeadCSVExportView.as_view(), name='csv_export'),
    # Campos personalizados
    path('campos/', views.CampoListView.as_view(), name='campos'),
    path('campos/nuevo/', views.CampoCreateView.as_view(), name='campo_create'),
    path('campos/<int:pk>/editar/', views.CampoUpdateView.as_view(), name='campo_update'),
    path('campos/<int:pk>/eliminar/', views.CampoDeleteView.as_view(), name='campo_delete'),
    path('campos/<int:pk>/toggle/', views.CampoToggleView.as_view(), name='campo_toggle'),
    path('asignar-masivo/', views.LeadBulkAssignView.as_view(), name='bulk_assign'),
]
