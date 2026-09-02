export interface DeviceSpec {
  category: string;
  spec_key: string;
  spec_value: string;
  spec_unit?: string;
}

export interface DeviceAlarm {
  priority?: string;
  condition: string;
  text_shown?: string;
  indicator_light?: string;
  indicator_sound: boolean;
  required_action?: string;
  alarm_order?: number;
}

export interface SerialCommand {
  direction?: string;
  command_name: string;
  description?: string;
  laser_a_mapping?: string;
  laser_b_mapping?: string;
  command_order?: number;
}

export interface DeviceDocument {
  id: string;
  device_id: string;
  filename: string;
  file_size: number;
  content_type?: string;
  created_at?: string;
}

export interface Device {
  id: string;
  name: string;
  model?: string;
  document_code?: string;
  safety_class: string;
  driver_version?: string;
  gui_version?: string;
  created_at?: string;
  specs: DeviceSpec[];
  alarms: DeviceAlarm[];
  commands: SerialCommand[];
  documents: DeviceDocument[];
}

export interface DeviceCreate {
  name: string;
  model?: string;
  document_code?: string;
  safety_class?: string;
  driver_version?: string;
  gui_version?: string;
  specs: DeviceSpec[];
  alarms: DeviceAlarm[];
  commands: SerialCommand[];
}

export interface DeviceUpdate {
  name?: string;
  model?: string;
  document_code?: string;
  safety_class?: string;
  driver_version?: string;
  gui_version?: string;
  specs?: DeviceSpec[];
  alarms?: DeviceAlarm[];
  commands?: SerialCommand[];
}

export interface ReferenceDocument {
  id: string;
  filename: string;
  template_name: string;
  section_count: number;
  version: number;
  is_active: boolean;
  created_at?: string;
}

export interface DeviceDocumentFigure {
  rel_id: string;
  alt_text: string | null;
  image_url: string | null;
}

export interface DeviceDocumentSection {
  section_name: string;
  section_type: string;
  heading_level: number;
  parent_section: string | null;
  section_order: number | null;
  content_preview: string;
  figures: DeviceDocumentFigure[];
}

export interface ReferenceSection {
  section_name: string;
  section_type: string;
  heading_level: number;
  parent_section: string | null;
  section_order: number;
  content_preview: string;
}

export interface GeneratedDocument {
  id: string;
  device_id: string;
  reference_doc_id?: string;
  status: string;
  progress_pct: number;
  current_section?: string;
  result_sections?: Record<string, string>;
  file_path?: string;
  generation_log?: string;
  error_message?: string;
  created_at?: string;
  completed_at?: string;
  version: number;
}

export interface DocumentHistoryItem {
  job_id: string;
  version: number;
  status: string;
  created_at?: string;
  completed_at?: string;
}

export interface DeviceListResponse {
  items: Device[];
  total: number;
  skip: number;
  limit: number;
}
