from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('', views.index, name='index'),
    path("buscar-projetos/", views.buscar_projetos, name="buscar_projetos"),
    path("buscar-pessoa/", views.buscar_pessoa_por_documento, name="buscar_pessoa"),
    path("importar-vertices/", views.importar_vertices_lisp, name="importar_vertices_lisp"),
    path("importar-vertices-completos/<int:projeto_id>/", views.importar_dados_completos, name="importar_dados_completos"),

     ]