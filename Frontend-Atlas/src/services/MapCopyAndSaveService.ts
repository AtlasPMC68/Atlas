import keycloak from "../keycloak";
import { camelToSnake, snakeToCamel } from "../utils/utils";
import type {
  CreateMapInput,
  CreateMapResponse,
  MapMeta,
} from "../typescript/mapMeta";
import type { FeatureForSave } from "../typescript/feature";

export class MapCopyAndSaveService {
  static async getMapMeta(mapId: string): Promise<MapMeta> {
    const response = await fetch(
      `${import.meta.env.VITE_API_URL}/maps/${mapId}`,
      {
        headers: {
          Authorization: `Bearer ${keycloak.token}`,
        },
      },
    );

    if (!response.ok) {
      throw new Error(`Error fetching map metadata: ${response.status}`);
    }

    return snakeToCamel(await response.json()) as MapMeta;
  }

  static async createMap(input: CreateMapInput): Promise<CreateMapResponse> {
    const response = await fetch(
      `${import.meta.env.VITE_API_URL}/maps/create`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${keycloak.token}`,
        },
        body: JSON.stringify(camelToSnake(input)),
      },
    );

    if (!response.ok) {
      throw new Error(`Error creating map: ${response.status}`);
    }

    return snakeToCamel(await response.json()) as CreateMapResponse;
  }

  static async saveFeatures(mapId: string, features: FeatureForSave[]): Promise<void> {
    const response = await fetch(
      `${import.meta.env.VITE_API_URL}/maps/features/${mapId}`,
      {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${keycloak.token}`,
        },
        body: JSON.stringify(camelToSnake(features)),
      },
    );

    if (!response.ok) {
      throw new Error(`Error saving features: ${response.status}`);
    }
  }
}