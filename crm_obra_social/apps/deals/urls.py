from django.urls import path
from . import views

app_name = 'deals'

urlpatterns = [
    # Kanban
    path('',                           views.DealKanbanView.as_view(),    name='kanban'),
    # List
    path('lista/',                     views.DealListView.as_view(),      name='list'),
    # Deal CRUD
    path('nuevo/',                     views.DealCreateView.as_view(),    name='create'),
    path('<int:pk>/',                  views.DealDetailView.as_view(),    name='detail'),
    path('<int:pk>/editar/',           views.DealUpdateView.as_view(),    name='update'),
    path('<int:pk>/eliminar/',         views.DealDeleteView.as_view(),    name='delete'),
    path('<int:pk>/mover/',            views.DealMoveView.as_view(),      name='move'),
    # Pipelines
    path('pipelines/',                 views.PipelineListView.as_view(),  name='pipeline_list'),
    path('pipelines/nuevo/',           views.PipelineCreateView.as_view(), name='pipeline_create'),
    path('pipelines/<int:pk>/editar/', views.PipelineUpdateView.as_view(), name='pipeline_update'),
    path('pipelines/<int:pk>/eliminar/', views.PipelineDeleteView.as_view(), name='pipeline_delete'),
    # Stage management
    path('etapas/<int:pk>/eliminar/', views.StageDeleteView.as_view(),   name='stage_delete'),
    # APIs
    path('api/stages/<int:pipeline_pk>/', views.StagesAPIView.as_view(), name='stages_api'),
    path('api/contactos/',            views.ContactoSearchAPIView.as_view(), name='contacto_search'),
]
