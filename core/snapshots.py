BUSINESSES_SCHEMA = {
    "address":             "string",   # PK
    "business_name":       "string",   # "" per building vuoto
    "business_type":       "string",   # ba:businesstype_*
    "rent_per_day":        "float64",
    "temporarily_closed":  "bool",
    "customer_capacity":   "int32",
    "sat_overall":         "float64",
    "sat_customer_service":"float64",
    "sat_pricing":         "float64",
    "sat_cleanliness":     "float64",
    "sat_facility":        "float64",
    "promotion_total":     "float64",
    "promotion_marketing": "float64",
    "radio_station":       "int32",
    "warned_no_employee":  "bool",
}

OPENING_HOURS_SCHEMA = {          # una riga per fascia oraria
    "address":    "string",
    "day":        "int32",        # 1-7
    "is_open":    "bool",
    "start_hour": "int32",
    "end_hour":   "int32",
}

SHIFTS_SCHEMA = {                 # una riga per turno
    "address":         "string",
    "day":             "int32",
    "employee_id":     "string",
    "start_hour":      "int32",
    "end_hour":        "int32",
    "station_item_id": "string",
    "shift_type":      "int32",    # 0/1, significato da confermare
}

EMPLOYEES_SCHEMA = {
    "employee_id":          "string",   # PK
    "name":                 "string",
    "address":              "string",   # "" se non assegnato
    "hourly_wage":          "float64",
    "satisfaction":         "float64",
    "weekly_hours":         "int32",
    "is_absent":            "bool",
    "is_complaining":       "bool",
    "complaint_demand":     "string",   # "" se nessuna
    "quit_warning":         "bool",
    "hr_plan_id":           "string",
    "has_health_insurance": "bool",
}

IMPORTS_SCHEMA = {                # una riga per partnership × prodotto
    "partnership_id":    "string",
    "import_address":    "string",   # il pier
    "is_active":         "bool",
    "is_repeating":      "bool",
    "next_delivery_day": "int32",
    "item_key":          "string",
    "amount":            "int32",
    "ordered_last_week": "int32",
    "warehouse_address": "string",   # "" se nessuno
}

FULFILLED_DEMANDS_SCHEMA = {      # una riga per business × domanda soddisfatta
    "address":    "string",
    "demand_key": "string",       # ba:customerdemand_*
}