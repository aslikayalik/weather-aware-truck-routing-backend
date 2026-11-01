import operator
from functools import reduce

from django.db.models import F, Q, Value, TextField
from django.db.models.functions import Cast, Lower, Replace
from rest_framework.filters import SearchFilter


def _normalize_turkish_value(value):
    if value is None:
        return ""
    normalized = (
        value.replace("\u0130", "i")
        .replace("\u0131", "i")
        .lower()
    )
    normalized = normalized.replace("\u0307", "")
    return (
        normalized.replace("\u00e7", "c")
        .replace("\u011f", "g")
        .replace("\u015f", "s")
        .replace("\u00f6", "o")
        .replace("\u00fc", "u")
    )


def _normalize_turkish_expr(field_name):
    expr = Cast(F(field_name), output_field=TextField())
    expr = Replace(
        expr, Value("\u0130"), Value("i"), output_field=TextField()
    )
    expr = Replace(
        expr, Value("\u0131"), Value("i"), output_field=TextField()
    )
    expr = Lower(expr, output_field=TextField())
    expr = Replace(
        expr, Value("\u0307"), Value(""), output_field=TextField()
    )
    expr = Replace(expr, Value("\u00e7"), Value("c"), output_field=TextField())
    expr = Replace(expr, Value("\u011f"), Value("g"), output_field=TextField())
    expr = Replace(expr, Value("\u015f"), Value("s"), output_field=TextField())
    expr = Replace(expr, Value("\u00f6"), Value("o"), output_field=TextField())
    return Replace(expr, Value("\u00fc"), Value("u"), output_field=TextField())


class TurkishSearchFilter(SearchFilter):
    def filter_queryset(self, request, queryset, view):
        search_fields = self.get_search_fields(view, request)
        search_terms = self.get_search_terms(request)

        if not search_fields or not search_terms:
            return queryset

        orm_lookups = []
        for search_field in search_fields:
            field_name = str(search_field)
            try:
                orm_lookup = self.construct_search(field_name, queryset)
            except TypeError:
                orm_lookup = self.construct_search(field_name)
            orm_lookups.append(orm_lookup)

        annotations = {}
        normalized_lookups = []
        passthrough_lookups = []

        for idx, orm_lookup in enumerate(orm_lookups):
            try:
                field_name, lookup = orm_lookup.rsplit("__", 1)
            except ValueError:
                passthrough_lookups.append(orm_lookup)
                continue

            if lookup in ("icontains", "istartswith", "iexact"):
                alias = f"_tr_search_{idx}"
                annotations[alias] = _normalize_turkish_expr(field_name)
                normalized_lookups.append((alias, lookup))
            else:
                passthrough_lookups.append(orm_lookup)

        if annotations:
            queryset = queryset.annotate(**annotations)

        for term in search_terms:
            normalized_term = _normalize_turkish_value(term)
            queries = []

            for alias, lookup in normalized_lookups:
                if lookup == "icontains":
                    lookup_expr = f"{alias}__contains"
                elif lookup == "istartswith":
                    lookup_expr = f"{alias}__startswith"
                else:
                    lookup_expr = f"{alias}__exact"
                queries.append(Q(**{lookup_expr: normalized_term}))

            for orm_lookup in passthrough_lookups:
                queries.append(Q(**{orm_lookup: term}))

            if queries:
                queryset = queryset.filter(reduce(operator.or_, queries))

        if hasattr(self, "must_call_distinct") and self.must_call_distinct(
            queryset, search_fields
        ):
            queryset = queryset.distinct()

        return queryset
