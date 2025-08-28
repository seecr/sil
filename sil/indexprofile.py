class IndexProfile:
    def __init__(self, fields):
        self._fields = {field.name: field for field in fields}

        unqualified_fields = [f for f in fields if f.is_unqualified]
        if len(unqualified_fields) > 1:
            raise RuntimeError("Multiple unqualified fields")
        self._unqualified_field = (
            unqualified_fields[0] if len(unqualified_fields) == 1 else None
        )

    @property
    def unqualified(self):
        return self._unqualified_field

    @property
    def fields(self):
        return list(self._fields.values())

    def suggest_fields(self):
        return [field for field in self._fields.values() if field.is_suggest]

    def sortable_fields(self):
        return [field for field in self._fields.values() if field.is_sortable]

    def get(self, name):
        return self._fields.get(name)
