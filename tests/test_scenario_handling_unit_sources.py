import unittest

from proteus import Model
from trytond.modules.company.tests.tools import create_company, get_company
from trytond.pool import Pool
from trytond.tests.test_tryton import DB_NAME, drop_db
from trytond.tests.tools import activate_modules
from trytond.transaction import Transaction


class TestHandlingUnitSources(unittest.TestCase):

    def setUp(self):
        drop_db()
        super().setUp()

    def tearDown(self):
        drop_db()
        super().tearDown()

    def test(self):
        config = activate_modules('production_handling_unit')
        create_company(config=config)
        company = get_company()
        Unit = Model.get('production.handling_unit')
        first = Unit(name='Trolley', company=company)
        first.save()
        second = Unit(name='Pallet', company=company)
        second.save()
        Operation = Model.get('production.routing.operation')
        operation = Operation(name='Packing')
        operation.save()
        consumer = Operation(name='Dispatch',
            handling_unit_source_operations=[operation])
        consumer.save()
        Routing = Model.get('production.routing')
        routing = Routing(name='Packing route')
        routing.steps.new(operation=operation, sequence=10,
            handling_unit=first)
        routing.steps.new(operation=operation, sequence=20,
            handling_unit=second, show_handling_unit_values=False)
        routing.steps.new(operation=consumer, sequence=30)
        routing.save()
        routing.reload()
        self.assertTrue(routing.steps[0].show_handling_unit_values)
        self.assertFalse(routing.steps[1].show_handling_unit_values)
        with Transaction().start(DB_NAME, 1, context=config.context):
            pool = Pool()
            Step = pool.get('production.routing.step')
            Production = pool.get('production')
            Company = pool.get('company.company')
            Cycle = pool.get('production.work.cycle')
            production = Production(company=Company(company.id), work_center=None)
            works = [Step(step.id).get_work(production, None)
                for step in routing.steps]
            self.assertEqual(works[0].routing_step.id, routing.steps[0].id)
            self.assertEqual(
                Cycle._get_handling_unit_from_work(works[0]).id, first.id)
            self.assertIsNone(Cycle._get_handling_unit_from_work(works[1]))
            self.assertEqual(
                Cycle._get_handling_unit_from_work(works[2]).id, first.id)
