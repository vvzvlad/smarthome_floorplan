/**
 * Configuration Migration Utility
 *
 * Migrates older configurations where onColor/offColor were top-level style properties
 * to the new colors: {onColor, offColor} structure.
 */

import type { FloorplanConfig } from '../types/floorplan';
import { v4 as uuidv4 } from 'uuid';

/**
 * Migrates an individual entity's color properties from old to new format
 * @param entity The entity configuration to migrate
 * @returns The migrated entity (modifies in place and returns)
 */
function migrateEntityColors(entity: any): any {
    // Skip if entity already has the new colors structure
    if (entity.style?.colors) {
        return entity;
    }

    // Skip if no style object
    if (!entity.style) {
        return entity;
    }

    const style = entity.style;

    if (style.onColor || style.offColor) {
        style.colors = {
            onColor: style.onColor || '#facc15',
            offColor: style.offColor || '#94a3b8'
        };
        delete style.onColor;
        delete style.offColor;
    }

    return entity;
}

/**
 * Migrates a full configuration from old to new format
 * @param config The floorplan configuration to migrate
 * @returns The migrated configuration
 */
export function migrateConfig(config: any): FloorplanConfig {
    // Ensure entities array exists
    if (!config.entities || !Array.isArray(config.entities)) {
        return config as FloorplanConfig;
    }

    // Migrate each entity
    config.entities = config.entities.map((entity: any) => migrateEntityColors(entity));

    return config as FloorplanConfig;
}

/**
 * Checks if a configuration needs migration
 * @param config The configuration to check
 * @returns True if migration is needed
 */
export function needsMigration(config: any): boolean {
    if (!config.entities || !Array.isArray(config.entities)) {
        return false;
    }

    return config.entities.some((entity: any) => {
        if (!entity.style) return false;
        const hasOldColors = Boolean(entity.style.onColor || entity.style.offColor);
        const hasNewColors = Boolean(entity.style.colors);
        return hasOldColors && !hasNewColors;
    });
}

/**
 * Validate and normalize a parsed JSON value into a FloorplanConfig for import.
 * Throws an Error with a user-facing message when the value is not a usable
 * floorplan config. Applies the same normalization used when loading from the
 * server: strips whitespace from the image Data URI and runs the color-format
 * migration. Intended for re-importing a previously exported config.
 */
export function normalizeImportedConfig(raw: unknown): FloorplanConfig {
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
        throw new Error('Config must be a JSON object');
    }
    const obj = raw as Record<string, unknown>;
    if (!Array.isArray(obj.entities)) {
        throw new Error('Config is missing an "entities" array');
    }
    // Every entity must at least be an object (guards against garbage files).
    if (obj.entities.some((e) => !e || typeof e !== 'object' || Array.isArray(e))) {
        throw new Error('Config contains an invalid entity');
    }
    // Normalize image Data URI (strip stray whitespace/newlines), like initApp does.
    obj.imageBase64 = typeof obj.imageBase64 === 'string' ? obj.imageBase64.replace(/\s/g, '') : '';
    if (typeof obj.name !== 'string') obj.name = 'Imported Floorplan';
    if (typeof obj.id !== 'string' || obj.id === '') obj.id = uuidv4();
    let config = obj as unknown as FloorplanConfig;
    if (needsMigration(config)) config = migrateConfig(config);
    return config;
}
