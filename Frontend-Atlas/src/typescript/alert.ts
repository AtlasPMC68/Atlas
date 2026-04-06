export type AlertType = "success" | "error";

export type AlertState = {
  type: AlertType;
  message: string;
} | null;