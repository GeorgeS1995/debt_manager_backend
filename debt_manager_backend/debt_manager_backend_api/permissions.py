from rest_framework import permissions


class DebtorPermission(permissions.BasePermission):
    message = 'You are not the owner of the object'

    def has_object_permission(self, request, view, obj):
        active = obj.is_active
        if active:
            return obj.owner == request.user
        return active


class IsAuthenticatedOrCreateOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.method == 'POST' or
            request.user and
            request.user.is_authenticated
        )
