"""
Schedule Models - Data Classes
Core data structures for Schedule Optimizer
"""
from dataclasses import dataclass, field
from typing import Literal, List, Dict

# ============================================================================
# BUILDING
# ============================================================================

@dataclass
class Building:
    """Represents a business building with capacity limit"""
    business_type: str  # 'Retail', 'Office', 'Warehouse'
    code: str           # 'M1', 'K1', 'A1', etc.
    capacity_limit: int # Maximum customers per hour
    
    def __str__(self):
        return f"{self.code} ({self.business_type}) - Max {self.capacity_limit} customers/hour"


# ============================================================================
# EMPLOYEE DEMAND
# ============================================================================

@dataclass
class Demand:
    """Represents a single employee demand/constraint"""
    category: Literal['schedule', 'benefits', 'environment', 'equipment']
    constraint: str  # e.g., 'full_time', 'gold_insurance', 'Office Chair'
    priority: Literal['critical', 'important', 'nice_to_have']
    
    def __str__(self):
        return f"{self.constraint} ({self.priority})"


# ============================================================================
# EMPLOYEE
# ============================================================================

@dataclass
class Employee:
    """Represents an employee with wage, role, and demands"""
    name: str
    role: str                    # e.g., 'Customer Service', 'Cleaning', 'Office Worker'
    hourly_wage: float          # $/hour
    demands: List[Demand] = field(default_factory=list)
    
    def __str__(self):
        return f"{self.name} ({self.role}) - ${self.hourly_wage:.2f}/h - {len(self.demands)} demands"
    
    @property
    def critical_demands(self) -> List[Demand]:
        """Get only critical priority demands"""
        return [d for d in self.demands if d.priority == 'critical']
    
    @property
    def important_demands(self) -> List[Demand]:
        """Get only important priority demands"""
        return [d for d in self.demands if d.priority == 'important']
    
    @property
    def nice_to_have_demands(self) -> List[Demand]:
        """Get only nice-to-have priority demands"""
        return [d for d in self.demands if d.priority == 'nice_to_have']


# ============================================================================
# OPERATING HOURS
# ============================================================================

@dataclass
class DailySchedule:
    """Represents operating hours for a single day"""
    day_name: Literal['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    is_open: bool = True
    start_hour: int = 8   # 24-hour format (0-23)
    end_hour: int = 22    # 24-hour format (0-23)
    
    @property
    def hours_open(self) -> int:
        """Calculate total hours open for the day"""
        if not self.is_open:
            return 0
        return self.end_hour - self.start_hour
    
    def __str__(self):
        if not self.is_open:
            return f"{self.day_name}: Closed"
        return f"{self.day_name}: {self.start_hour:02d}:00-{self.end_hour:02d}:00 ({self.hours_open}h)"


# ============================================================================
# BUSINESS SETUP (Complete Configuration)
# ============================================================================

@dataclass
class BusinessSetup:
    """Complete business configuration for schedule optimization"""
    building: Building
    employees: List[Employee] = field(default_factory=list)
    weekly_schedule: List[DailySchedule] = field(default_factory=list)
    
    @property
    def total_weekly_hours(self) -> int:
        """Calculate total operating hours per week"""
        return sum(day.hours_open for day in self.weekly_schedule)
    
    @property
    def total_employees(self) -> int:
        """Get total number of employees"""
        return len(self.employees)
    
    @property
    def total_weekly_labor_cost(self) -> float:
        """Calculate total weekly labor cost (assuming full hours for all employees)"""
        # This is a simple estimate - actual cost depends on shift assignments
        weekly_cost = 0
        for employee in self.employees:
            # Assume employee works proportional to store hours (simplified)
            weekly_cost += employee.hourly_wage * self.total_weekly_hours
        return weekly_cost
    
    def __str__(self):
        return (
            f"Business Setup:\n"
            f"  Building: {self.building}\n"
            f"  Employees: {self.total_employees}\n"
            f"  Weekly Hours: {self.total_weekly_hours}h\n"
        )
        
        

# ============================================================================
# OPTIMIZATION RESULT
# ============================================================================


@dataclass
class OptimizationResult:
    """Result of schedule optimization"""
    success: bool
    status: str
    total_cost: float
    total_satisfaction: float
    schedule: Dict[str, Dict[str, List[str]]]  # employee -> day -> [shifts]
    daily_shifts: Dict[str, Dict[str, dict]]   # day -> shift_name -> shift_info
    unmet_demands: List[str]
    solver_time: float