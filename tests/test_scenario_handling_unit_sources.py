import unittest
from types import SimpleNamespace

from trytond.modules.production_handling_unit.production import WorkCycle
from trytond.tests.test_tryton import drop_db


class TestHandlingUnitSources(unittest.TestCase):

    def setUp(self):
        drop_db()
        super().setUp()

    def tearDown(self):
        drop_db()
        super().tearDown()

    def test(self):
        source_handling_unit = SimpleNamespace(id=11)
        source_operation = SimpleNamespace(
            id=22,
            handling_unit=source_handling_unit,
        )
        work = SimpleNamespace(
            operation=SimpleNamespace(
                handling_unit=None,
                handling_unit_source_operations=[source_operation],
            ),
        )

        self.assertIs(
            WorkCycle._get_operation_handling_unit_from_work(work),
            source_handling_unit)
