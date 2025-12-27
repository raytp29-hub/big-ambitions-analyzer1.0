"""
Temporary test script for schedule optimizer
"""

from analysis.schedule_models import Employee, DailySchedule, BusinessSetup, Building, Demand, OptimizationResult
from analysis.schedule_optimizer import optimize_schedule

import inspect

print("\n=== DIAGNOSTIC CHECK ===")
print(f"OptimizationResult fields: {OptimizationResult.__dataclass_fields__.keys()}")
print("========================\n")



# Mock data for testing
def test_basic_optimization():
    # 1. Create mock business
    building = Building(
        business_type='Retail',
        code='M1',
        capacity_limit=60
    )
    
    business_setup = BusinessSetup(
        building=building,
        employees=[],  # Will be filled below
        weekly_schedule=[]  # Will be filled below
    )
    
    # 2. Create mock employees
    employees = [
    Employee(
        name='John',
        role='Customer Service',
        hourly_wage=15.0,
        demands=[
            Demand(category='schedule', constraint='full_time', priority='critical'),
            Demand(category='schedule', constraint='no_weekend', priority='important')
        ]
    ),
    Employee(
        name='Jane',
        role='Customer Service',
        hourly_wage=16.0,
        demands=[
            Demand(category='schedule', constraint='part_time', priority='critical')
        ]
    ),
    Employee(
        name='marti',  # ← NUOVO!
        role='Customer Service',
        hourly_wage=14.0,
        demands=[
            Demand(category='schedule', constraint='part_time', priority='critical')
        ]
    ),
    Employee(
    name='Bob',
    role='Customer Service',
    hourly_wage=14.0,
    demands=[
        Demand(category='schedule', constraint='part_time', priority='critical'),
        Demand(category='schedule', constraint='no_cleaning', priority='critical')  # ← NUOVO!
        ]
    )
]
    
    # 3. Create mock weekly schedule
    weekly_schedule = [
        DailySchedule('Monday', is_open=True, start_hour=14, end_hour=24),
        DailySchedule('Tuesday', is_open=True, start_hour=10, end_hour=22),
        DailySchedule('Wednesday', is_open=True, start_hour=10, end_hour=22),
        DailySchedule('Thursday', is_open=True, start_hour=10, end_hour=22),
        DailySchedule('Friday', is_open=True, start_hour=10, end_hour=22),
        DailySchedule('Saturday', is_open=False, start_hour=10, end_hour=22),
        DailySchedule('Sunday', is_open=False, start_hour=0, end_hour=0)
    ]
    
    # 4. Run optimization
    print("Starting optimization test...\n")
    
    
    
    result = optimize_schedule(
        business_setup=business_setup,
        employees=employees,
        weekly_schedule=weekly_schedule,
        max_simultaneous=3,
        alpha=1.0,
        beta=0.5
    )
    
    # 5. Show results
    print("\n" + "="*60)
    print("OPTIMIZATION RESULT")
    print("="*60)
    print(f"Success: {result.success}")
    print(f"Status: {result.status}")
    print(f"Total Cost: ${result.total_cost:.2f}")
    print(f"Total Satisfaction: {result.total_satisfaction:.1f}%")
    print(f"Solver Time: {result.solver_time:.2f}s")
    print("="*60)

if __name__ == "__main__":
    test_basic_optimization()