/** 家庭饮食预算周期。 */
export type FamilyDietaryBudgetPeriod = 1 | 2 | 3;

/** 家庭饮食档案。 */
export interface FamilyDietaryProfile {
  id: number;
  family_id: number;
  budget_min: number | null;
  budget_max: number | null;
  budget_currency: string;
  budget_period: FamilyDietaryBudgetPeriod;
  notes: string;
  updated_by: number;
  created_at: string;
  updated_at: string;
}

/** 保存家庭饮食档案的请求参数。 */
export interface FamilyDietaryProfileInput {
  budget_min: number | null;
  budget_max: number | null;
  budget_currency: string;
  budget_period: FamilyDietaryBudgetPeriod;
  notes: string;
}
