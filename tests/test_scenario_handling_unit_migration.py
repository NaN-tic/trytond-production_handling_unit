import unittest

from proteus import Model
from trytond.modules.company.tests.tools import create_company, get_company
from trytond.pool import Pool
from trytond.tests.test_tryton import DB_NAME, drop_db
from trytond.tests.tools import activate_modules
from trytond.transaction import Transaction


class TestHandlingUnitMigration(unittest.TestCase):

    def setUp(self):
        drop_db()
        super().setUp()

    def tearDown(self):
        drop_db()
        super().tearDown()

    def test(self):
        config = activate_modules('production_handling_unit')
        create_company(config=config)
        Unit = Model.get('production.handling_unit')
        unit = Unit(name='Legacy trolley', company=get_company())
        unit.save()
        Operation = Model.get('production.routing.operation')
        operation = Operation(name='Legacy operation')
        operation.save()
        Routing = Model.get('production.routing')
        routing = Routing(name='Legacy routing')
        routing.steps.new(operation=operation, sequence=10)
        routing.steps.new(operation=operation, sequence=20)
        routing.save()
        first_step_id = routing.steps[0].id
        with Transaction().start(DB_NAME, 1, context=config.context):
            pool = Pool()
            Step = pool.get('production.routing.step')
            Operation = pool.get('production.routing.operation')
            handler = Operation.__table_handler__('production_handling_unit')
            handler.add_column('handling_unit', 'INTEGER')
            handler.add_column('show_handling_unit_values', 'BOOLEAN')
            table = Operation.__table__()
            cursor = Transaction().connection.cursor()
            cursor.execute(*table.update(
                [table.handling_unit, table.show_handling_unit_values],
                [unit.id, False], where=table.id == operation.id))
            handler = Step.__table_handler__('production_handling_unit')
            handler.drop_column('handling_unit')
            handler.drop_column('show_handling_unit_values')
            Step.__register__('production_handling_unit')
            step = Step.__table__()
            cursor.execute(*step.select(
                step.handling_unit, step.show_handling_unit_values,
                where=step.routing == routing.id, order_by=step.sequence))
            self.assertEqual(cursor.fetchall(), [(unit.id, False)] * 2)
            cursor.execute(*step.update(
                [step.handling_unit, step.show_handling_unit_values],
                [None, True], where=step.id == first_step_id))
            Step.__register__('production_handling_unit')
            cursor.execute(*step.select(
                step.handling_unit, step.show_handling_unit_values,
                where=step.routing == routing.id, order_by=step.sequence))
            self.assertEqual(cursor.fetchall(), [(None, True), (unit.id, False)])
