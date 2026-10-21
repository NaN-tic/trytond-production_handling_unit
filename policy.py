from itertools import combinations

from trytond.exceptions import UserError
from trytond.i18n import gettext
from trytond.model import ModelSQL, ModelView, Unique, fields
from trytond.pool import Pool
from trytond.pyson import Eval
from trytond.transaction import Transaction


class OperationHandlingUnit(ModelSQL, ModelView):
    'Operation Handling Unit Configuration'
    __name__ = 'production.operation.handling_unit'

    operation = fields.Many2One('production.routing.operation', 'Operation',
        required=True, ondelete='CASCADE')
    company = fields.Many2One('company.company', 'Company', required=True)
    mode = fields.Selection([
        ('none', 'Do Not Request'), ('input', 'Enter Container'),
        ('previous', 'Retrieve Previous Container'),
        ], 'Handling Unit Behaviour', required=True)
    handling_unit = fields.Many2One('production.handling_unit', 'Handling Unit',
        domain=[('company', '=', Eval('company', -1))], depends=['company'])
    number_required = fields.Boolean('Container Number Required')
    uom = fields.Many2One('product.uom', 'UoM',
        help='Leave empty to use the production unit.')
    show_missing_units = fields.Boolean('Request Missing Units')

    @staticmethod
    def default_company():
        return Transaction().context.get('company')

    @staticmethod
    def default_mode():
        return 'none'

    @classmethod
    def __setup__(cls):
        super().__setup__()
        table = cls.__table__()
        cls._sql_constraints += [
            ('operation_company_unique', Unique(table, table.operation,
                table.company), 'production_handling_unit.msg_policy_unique')]


class StepHandlingUnitException(ModelSQL, ModelView):
    'Step Handling Unit Exception'
    __name__ = 'production.step.handling_unit.exception'

    step = fields.Many2One('production.routing.step', 'Step',
        required=True, ondelete='CASCADE')
    request = fields.Boolean('Request Handling Unit')
    products = fields.Many2Many('production.step.hu.exception-product',
        'exception', 'product', 'Products')
    categories = fields.Many2Many('production.step.hu.exception-category',
        'exception', 'category', 'Categories',
        help='Includes subcategories. Product exceptions take precedence.')

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls.__access__.add('step')

    @classmethod
    def validate(cls, exceptions):
        super().validate(exceptions)
        Category = Pool().get('product.category')
        Product = Pool().get('product.product')
        for step in {rule.step for rule in exceptions}:
            rules = list(step.handling_unit_exceptions)
            categories = {}
            for rule in rules:
                if not rule.products and not rule.categories:
                    raise UserError(gettext(
                        'production_handling_unit.msg_exception_empty'))
                roots = [category.id for category in rule.categories]
                categories[rule.id] = set(roots)
                if roots:
                    categories[rule.id].update(category.id for category in
                        Category.search([('parent', 'child_of', roots)]))
            for first, second in combinations(rules, 2):
                if first.request == second.request:
                    continue
                conflict = bool(set(first.products) & set(second.products))
                left, right = categories[first.id], categories[second.id]
                conflict |= bool(left & right)
                if not conflict and left and right:
                    with Transaction().set_context(active_test=False):
                        conflict = bool(Product.search([
                            ('template.categories', 'in', list(left)),
                            ('template.categories', 'in', list(right)),
                            ], limit=1))
                if conflict:
                    raise UserError(gettext(
                        'production_handling_unit.msg_exception_conflict',
                        step=step.rec_name))


class ExceptionProduct(ModelSQL):
    'Handling Unit Exception - Product'
    __name__ = 'production.step.hu.exception-product'
    exception = fields.Many2One('production.step.handling_unit.exception',
        'Exception', required=True, ondelete='CASCADE')
    product = fields.Many2One('product.product', 'Product',
        required=True, ondelete='CASCADE')

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls.__access__.add('exception')


class ExceptionCategory(ModelSQL):
    'Handling Unit Exception - Category'
    __name__ = 'production.step.hu.exception-category'
    exception = fields.Many2One('production.step.handling_unit.exception',
        'Exception', required=True, ondelete='CASCADE')
    category = fields.Many2One('product.category', 'Category',
        required=True, ondelete='CASCADE')

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls.__access__.add('exception')
