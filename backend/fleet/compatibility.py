from decimal import Decimal


def canonical_unit(value):
    key=str(value or "").strip().casefold()
    aliases={"tonne":"TONNE","tonnes":"TONNE","t":"TONNE","kg":"KG","kilogram":"KG","kilograms":"KG","cbm":"CBM","m3":"CBM","pallet":"PALLET","pallets":"PALLET"}
    return aliases.get(key,key.upper())


def load_compatibility(vehicle,order):
    required=order.required_vehicle_type.strip().upper()
    configured=vehicle.vehicle_type.strip().upper()
    if required and configured!=required:
        return False,f"Order requires {required}; truck type is {configured or 'not configured'}."
    if order.load_quantity is None:return None,"Order load quantity is missing; confirm legal load fit."
    if vehicle.capacity is None:return None,"Truck capacity is missing; configure it before booking."
    capacity_unit=canonical_unit(vehicle.capacity_unit);load_unit=canonical_unit(order.load_unit)
    if not capacity_unit or not load_unit:return None,"Capacity units are missing; verify truck and order units before booking."
    quantity=order.load_quantity
    if {capacity_unit,load_unit}=={"KG","TONNE"}:
        quantity=quantity*Decimal("1000") if load_unit=="TONNE" else quantity/Decimal("1000")
    elif capacity_unit!=load_unit:return False,f"Cannot compare {load_unit} with truck capacity in {capacity_unit}."
    if quantity>vehicle.capacity:return False,"Order load exceeds the truck's configured capacity after unit conversion."
    return True,"Configured vehicle type and capacity are compatible with the order."
