export type StandaloneRole = 'SYSTEM_ADMIN' | 'HEADMASTER' | 'TEACHER';

export type StandaloneUser = {
  id: string;
  username: string;
  displayName?: string | null;
  role: StandaloneRole;
  active: boolean;
};

export type StandaloneInstallation = {
  installationId: string;
  appVersion: string;
  schemaVersion: number;
};

export type StandaloneLicenseStatus = {
  active: boolean;
  reason: string;
  installationId: string;
  license?: {
    product: string;
    license_id: string;
    organization: string;
    installation_id: string;
    edition: string;
    valid_from: string;
    valid_until: string;
    max_schools: number;
    udise?: string;
  } | null;
};

export type StandaloneSchool = {
  id: string;
  code: string;
  udise_code: string;
  cluster_id: string;
  name_en: string;
  name_mr: string;
  village?: string | null;
  class_1_5_strength: number;
  class_6_8_strength: number;
  active: boolean;
};

export interface StandaloneDataService {
  initialize(): Promise<StandaloneInstallation>;
  getLicenseStatus(): Promise<StandaloneLicenseStatus>;
  activateLicense(packageJson: string): Promise<StandaloneLicenseStatus>;

  login(username: string, password: string): Promise<StandaloneUser>;
  logout(): Promise<void>;
  currentUser(): Promise<StandaloneUser | null>;

  listSchools(): Promise<StandaloneSchool[]>;
  getSchool(id: string): Promise<StandaloneSchool | null>;

  createBackup(): Promise<{ fileName: string; path: string; sha256?: string }>;
  restoreBackup(path: string): Promise<void>;
}
