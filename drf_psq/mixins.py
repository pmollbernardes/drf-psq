# -*- coding: utf-8 -*-

from rest_framework.permissions import BasePermission
from django.http import Http404

from .utils import and_permissions, get_caller_name, Rule


class PsqMixin(object):

    psq_rules = {}


    def _psq_get_view(self):
        if self.action is None:
            return None
        return getattr(self, self.action)


    def _psq_get_rules(self, view):
        if view is None:
            return []
        if hasattr(view, 'psq_rules'):
            return view.psq_rules

        vname = view.__name__
        for key, value in self.psq_rules.items():
            if key == vname or ((type(key) is tuple) and (vname in key)):
                return value

        return []


    def _psq_check(self, view):
        return self._psq_get_rules(view) not in [None, []]


    def _psq_get_permitted_rule(self, view):
        if self.request.user.is_superuser:
            return Rule()

        if hasattr(self, '_psq_permitted_rule'):
            return self._psq_permitted_rule

        psq_rules = self._psq_get_rules(view)
        if self.lookup_field in self.kwargs:
            obj = self.get_object()

        permitted_rule = None
        for rule in psq_rules:
            p = and_permissions(rule.permission_classes or self.permission_classes)()
            hp = p.has_permission(self.request, view)

            if (self.lookup_field in self.kwargs) and hp:
                current_obj = obj if (rule.get_obj is None) else rule.get_obj(self, obj)
                hop = p.has_object_permission(self.request, self, current_obj)
            elif hasattr(self, 'parent_lookup_field') and (self.parent_lookup_field in self.kwargs) and (rule.get_obj is not None) and hp:
                #Permission based on parent object for non-detail actions
                hop = p.has_object_permission(self.request, self, rule.get_obj(self))
            else:
                hop = True

            if hp and hop:
                permitted_rule = rule
                break

        self._psq_permitted_rule = permitted_rule
        return permitted_rule


    def get_object(self, *args, **kwargs):
        self.obj = self.obj if hasattr(self, 'obj') else super().get_object(*args, **kwargs)
        return self.obj


    def get_permissions(self):
        if self.action == 'metadata':
            return super().get_permissions()

        view = self._psq_get_view()
        if not self._psq_check(view):
            return super().get_permissions()

        rule = self._psq_get_permitted_rule(view)
        return [BasePermission()] if rule else [(~BasePermission)()]


    def get_serializer_class(self):
        if self.action == 'metadata':
            return super().get_serializer_class()

        view = self._psq_get_view()
        if not self._psq_check(view):
            return super().get_serializer_class()

        rule = self._psq_get_permitted_rule(view)
        if rule and rule.serializer_class:
            return rule.serializer_class

        return super().get_serializer_class()


    def get_queryset(self):
        if self.action == 'metadata':
            return super().get_queryset()

        view = self._psq_get_view()
        if not self._psq_check(view):
            return super().get_queryset()

        if get_caller_name() in [self.get_object.__name__, self.get_queryset.__name__]:
            return super().get_queryset()

        rule = self._psq_get_permitted_rule(view)
        if rule and rule.queryset:
            return rule.queryset(self)

        return super().get_queryset()


    def check_object_permissions(self, *args, **kwargs):
        if self.action == 'metadata':
            super().check_object_permissions(*args, **kwargs)

        view = self._psq_get_view()
        if not self._psq_check(view):
            super().check_object_permissions(*args, **kwargs)

        if get_caller_name() != self.get_object.__name__:
            super().check_object_permissions(*args, **kwargs)


    def _psq_remove_unallowed_filters(self):
        serializer_class = self.get_serializer_class()
        if not serializer_class:
            return

        query_params = self.request.query_params.copy()
        allowed_fields = serializer_class().get_fields().keys()
        all_fields = [
            field.name for field in serializer_class.Meta.model._meta.get_fields()
        ]

        for param in list(query_params.keys()):
            filter_field = param.split('__')[0]
            if (filter_field in all_fields) and (filter_field not in allowed_fields):
                query_params.pop(param)

        query_params._mutable = False
        self.request._request.GET = query_params


    def filter_queryset(self, *args, **kwargs):
        if get_caller_name() == self.get_object.__name__:
            return super().filter_queryset(*args, **kwargs)

        self._psq_remove_unallowed_filters()
        return super().filter_queryset(*args, **kwargs)
