# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.

from trytond.pool import Pool

from . import production, product, routing


def register():
    Pool.register(
        production.HandlingUnit,
        production.WorkCenterHandlingUnitAssignment,
        production.WorkCenter,
        production.WorkCycle,
        routing.RoutingOperationHandlingUnitSource,
        routing.RoutingOperation,
        product.Product,
        module='production_handling_unit', type_='model')
