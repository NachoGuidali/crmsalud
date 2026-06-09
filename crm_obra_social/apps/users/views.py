from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, UpdateView, ListView, DetailView, View

from .forms import LoginForm, UserCreateForm, UserUpdateForm, ProfileForm
from .models import User


class LoginView(View):
    template_name = 'users/login.html'

    def get(self, request):
        if request.user.is_authenticated:
            return redirect('reports:dashboard')
        form = LoginForm(request)
        return self._render(request, form)

    def post(self, request):
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            next_url = request.GET.get('next', 'reports:dashboard')
            return redirect(next_url)
        return self._render(request, form)

    def _render(self, request, form):
        from django.shortcuts import render
        return render(request, self.template_name, {'form': form})


class LogoutView(LoginRequiredMixin, View):
    def post(self, request):
        logout(request)
        return redirect('users:login')


class SupervisorRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.can_see_all_leads


class UserListView(LoginRequiredMixin, SupervisorRequiredMixin, ListView):
    model = User
    template_name = 'users/user_list.html'
    context_object_name = 'users'
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset().order_by('first_name', 'last_name')
        q = self.request.GET.get('q', '')
        if q:
            qs = qs.filter(username__icontains=q) | qs.filter(first_name__icontains=q) | qs.filter(last_name__icontains=q)
        return qs


class UserCreateView(LoginRequiredMixin, SupervisorRequiredMixin, CreateView):
    model = User
    form_class = UserCreateForm
    template_name = 'users/user_form.html'
    success_url = reverse_lazy('users:list')

    def form_valid(self, form):
        messages.success(self.request, 'Usuario creado correctamente.')
        return super().form_valid(form)


class UserUpdateView(LoginRequiredMixin, SupervisorRequiredMixin, UpdateView):
    model = User
    form_class = UserUpdateForm
    template_name = 'users/user_form.html'
    success_url = reverse_lazy('users:list')

    def form_valid(self, form):
        messages.success(self.request, 'Usuario actualizado correctamente.')
        return super().form_valid(form)


class ProfileView(LoginRequiredMixin, UpdateView):
    model = User
    form_class = ProfileForm
    template_name = 'users/profile.html'
    success_url = reverse_lazy('users:profile')

    def get_object(self):
        return self.request.user

    def form_valid(self, form):
        messages.success(self.request, 'Perfil actualizado correctamente.')
        return super().form_valid(form)


class HeartbeatView(LoginRequiredMixin, View):
    """Called every 60s by the browser to signal the agent is still active."""
    def post(self, request):
        User.objects.filter(pk=request.user.pk).update(ultimo_ping_at=timezone.now())
        return JsonResponse({'ok': True})


class ToggleDisponibleView(LoginRequiredMixin, View):
    """Manual on/off duty toggle from the sidebar."""
    def post(self, request):
        user = request.user
        nuevo = not user.disponible
        user.disponible = nuevo
        if nuevo:
            user.ultimo_ping_at = timezone.now()
        user.save(update_fields=['disponible', 'ultimo_ping_at'])
        return JsonResponse({'ok': True, 'disponible': nuevo})
