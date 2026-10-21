import unittest
from pathlib import Path

from proteus import Model
from trytond.exceptions import UserError
from trytond.i18n import gettext
from trytond.modules.company.tests.tools import create_company, get_company
from trytond.pool import Pool
from trytond.tests.test_tryton import DB_NAME, drop_db
from trytond.tests.tools import activate_modules
from trytond.transaction import Transaction


class TestHandlingUnitPolicy(unittest.TestCase):

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
        container = Unit(name='Trolley', company=company)
        container.save()
        Operation = Model.get('production.routing.operation')
        operation = Operation(name='Forming')
        operation.save()
        Configuration = Model.get('production.operation.handling_unit')
        configuration = Configuration(operation=operation, company=company,
            mode='input', handling_unit=container, number_required=True)
        configuration.save()
        Routing = Model.get('production.routing')
        routing = Routing(name='Common routing')
        routing.steps.new(operation=operation)
        routing.save()
        step, = routing.steps
        self.assertEqual(step.handling_unit_mode, 'inherit')
        Category = Model.get('product.category')
        parent = Category(name='No trolley')
        parent.save()
        child = Category(name='Child category', parent=parent)
        child.save()
        Other = Category(name='Other category')
        Other.save()
        Uom = Model.get('product.uom')
        unit, = Uom.find([('name', '=', 'Unit')])
        Template = Model.get('product.template')
        template = Template(name='Bread', type='goods', default_uom=unit,
            categories=[Category(child.id)])
        template.save()
        product, = template.products
        Rule = Model.get('production.step.handling_unit.exception')
        rule = Rule(step=step, request=False, categories=[Category(parent.id)])
        rule.save()
        with Transaction().start(DB_NAME, 1, context=config.context):
            pool = Pool()
            Work = pool.get('production.work')
            production = pool.get('production')(
                company=company.id, product=product.id)
            work = Work(production=production, operation=operation.id,
                routing_step=step.id, company=company.id)
            self.assertEqual(work.get_handling_unit_policy()['mode'], 'none')
        override = Rule(step=step, request=True, products=[Model.get('product.product')(product.id)])
        override.save()
        with Transaction().start(DB_NAME, 1, context=config.context):
            pool = Pool()
            work = pool.get('production.work')(
                production=pool.get('production')(
                    company=company.id, product=product.id),
                operation=operation.id, routing_step=step.id,
                company=company.id)
            policy = work.get_handling_unit_policy()
            self.assertEqual(policy['mode'], 'input')
            self.assertEqual(policy['handling_unit'].id, container.id)
            self.assertTrue(policy['number_required'])
        # Contradictory products, ancestors, and multi-category matches fail
        # through the actual write API, before reaching the production app.
        invalid = Rule(step=step, request=False, products=[Model.get('product.product')(product.id)])
        with self.assertRaises(UserError):
            invalid.save()
        invalid = Rule(step=step, request=True, categories=[Category(child.id)])
        with self.assertRaises(UserError):
            invalid.save()
        template.categories.append(Category(Other.id))
        template.save()
        invalid = Rule(step=step, request=True, categories=[Category(Other.id)])
        with self.assertRaises(UserError):
            invalid.save()
        with self.assertRaises(UserError):
            Rule(step=step, request=True).save()
        override.delete()
        rule.delete()
        step.handling_unit_mode = 'none'
        step.save()
        with Transaction().start(DB_NAME, 1, context=config.context):
            pool = Pool()
            work = pool.get('production.work')(
                production=pool.get('production')(
                    company=company.id, product=product.id),
                operation=operation.id, routing_step=step.id,
                company=company.id)
            self.assertEqual(work.get_handling_unit_policy()['mode'], 'none')
            self.assertIsNone(pool.get('production.work.cycle').
                _get_handling_unit_from_work(work))
        step.handling_unit_mode = 'inherit'
        step.save()
        configuration.mode = 'none'
        configuration.save()
        with Transaction().start(DB_NAME, 1, context=config.context):
            pool = Pool()
            work = pool.get('production.work')(
                production=pool.get('production')(
                    company=company.id, product=product.id),
                operation=operation.id, routing_step=step.id,
                company=company.id)
            self.assertEqual(work.get_handling_unit_policy()['mode'], 'none')
            Translation = pool.get('ir.translation')
            for language in ('es', 'ca'):
                Translation.translation_import(language,
                    'production_handling_unit', [str(
                        Path(__file__).resolve().parents[1]
                        / 'locale' / (language + '.po'))])
                with Transaction().set_context(language=language):
                    self.assertTrue(gettext(
                        'production_handling_unit.msg_exception_empty')
                        .startswith('Selecciona'))
