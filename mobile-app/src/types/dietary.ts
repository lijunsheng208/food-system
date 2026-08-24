/** 用户饮食偏好类型定义。 */

export type DietaryPreferenceType = 1 | 2 | 3 | 4 | 5;

/** 用户个人饮食偏好记录。 */
export interface UserDietaryPreference {
  id: number;
  preference_type: DietaryPreferenceType;
  preference_value: string;
  note: string;
  created_at: string;
  updated_at: string;
}

/** 保存个人饮食偏好时提交的记录。 */
export interface UserDietaryPreferenceInput {
  preference_type: DietaryPreferenceType;
  preference_value: string;
  note?: string;
}
