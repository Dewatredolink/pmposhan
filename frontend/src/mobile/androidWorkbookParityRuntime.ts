import { androidApiFetch } from './androidRuntime';
import { tryAndroidMasterApiFetch } from './androidMasterRuntime';
import { tryAndroidOperationsApiFetch } from './androidOperationsRuntime';
import { tryAndroidStockApiFetch } from './androidStockRuntime';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: {'Content-Type':'application/json'} });
}

function isIsoDate(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value);
}

function nonNegativeInt(value: string | null, fallback: number): number {
  if (value === null || value === '') return Math.max(0, Math.trunc(Number(fallback) || 0));
  const n = Number(value);
  return Number.isFinite(n) ? Math.max(0, Math.trunc(n)) : Math.max(0, Math.trunc(Number(fallback) || 0));
}

/**
 * Android-local implementation of the workbook ration preview.
 * It composes the already ported local school/menu/recipe/stock runtimes so the
 * web UI contract remains identical without needing FastAPI on Android.
 */
export async function tryAndroidWorkbookParityApiFetch(path: string, init: RequestInit = {}): Promise<Response | null> {
  const method = String(init.method || 'GET').toUpperCase();
  const url = new URL(path, 'https://local.pmposhan.invalid');
  const route = url.pathname;

  if (route !== '/workbook-parity/ration-preview') return null;
  if (method !== 'GET') return jsonResponse({detail:'METHOD_NOT_ALLOWED'},405);

  try {
    const schoolId = String(url.searchParams.get('school_id') || '');
    const rationDate = String(url.searchParams.get('ration_date') || '');
    if (!schoolId || !isIsoDate(rationDate)) {
      return jsonResponse({detail:'RATION_PREVIEW_FIELDS_INVALID'},400);
    }

    const schoolResponse = await androidApiFetch('/schools', {headers:init.headers || {}});
    if (!schoolResponse.ok) return schoolResponse;
    const schools = await schoolResponse.json();
    const school = Array.isArray(schools) ? schools.find((x:any)=>String(x.id)===schoolId) : null;
    if (!school) return jsonResponse({detail:'NO_SCHOOL_ACCESS'},403);

    const class15 = nonNegativeInt(url.searchParams.get('class_1_5'), Number(school.class_1_5_strength || 0));
    const class68 = nonNegativeInt(url.searchParams.get('class_6_8'), Number(school.class_6_8_strength || 0));

    const planResponse = await tryAndroidOperationsApiFetch(
      `/menu-plan?school_id=${encodeURIComponent(schoolId)}&menu_date=${rationDate}`,
      init,
    );
    if (!planResponse) return jsonResponse({detail:'ANDROID_MENU_PLAN_UNAVAILABLE'},501);
    if (!planResponse.ok) return planResponse;
    const planData = await planResponse.json();
    const plan = planData?.plan;
    if (!plan?.menu_id) return jsonResponse({detail:'No menu planned for this date'},404);

    const previewResponse = await tryAndroidMasterApiFetch(
      `/menus/${encodeURIComponent(String(plan.menu_id))}/recipe-preview?on_date=${rationDate}&class_1_5=${class15}&class_6_8=${class68}`,
      init,
    );
    if (!previewResponse) return jsonResponse({detail:'ANDROID_RECIPE_PREVIEW_UNAVAILABLE'},501);
    if (!previewResponse.ok) return previewResponse;
    const preview = await previewResponse.json();

    const balanceResponse = await tryAndroidStockApiFetch(
      `/stock/balances?school_id=${encodeURIComponent(schoolId)}`,
      init,
    );
    if (!balanceResponse) return jsonResponse({detail:'ANDROID_STOCK_BALANCE_UNAVAILABLE'},501);
    if (!balanceResponse.ok) return balanceResponse;
    const balances = await balanceResponse.json();
    const balanceMap = new Map<string,number>(
      (Array.isArray(balances) ? balances : []).map((x:any)=>[String(x.ingredient_id), Number(x.balance || 0)]),
    );

    const items = (Array.isArray(preview?.items) ? preview.items : []).map((x:any)=>{
      const required = Number(x.required_total || 0);
      const available = Number(balanceMap.get(String(x.ingredient_id)) || 0);
      return {
        ...x,
        required_total: required,
        available,
        shortage: Math.max(0, required - available),
      };
    });

    return jsonResponse({
      school_id: schoolId,
      ration_date: rationDate,
      menu: {
        id: String(plan.menu_id),
        code: plan.menu_code || null,
        name_en: plan.menu_name_en || null,
        name_mr: plan.menu_name_mr || null,
      },
      class_1_5: class15,
      class_6_8: class68,
      items,
    });
  } catch (error) {
    return jsonResponse({detail:error instanceof Error ? error.message : String(error)},400);
  }
}
