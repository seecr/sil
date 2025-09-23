## begin license ##
#
# "SIL"(Seecr Index Lib) makes developing index apps easier
#
# Copyright (C) 2025 Seecr (Seek You Too B.V.) https://seecr.nl
#
# This file is part of "Seecr Index Lib"
#
# "Seecr Index Lib" is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# "Seecr Index Lib" is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with "Seecr Index Lib"; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
#
## end license ##

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
