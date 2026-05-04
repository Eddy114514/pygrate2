/**
 * This file keeps the frontend payload shapes in one place.
 * It intentionally uses JSDoc instead of TypeScript so the app stays
 * lightweight while still documenting the contract with Flask.
 */

/**
 * @typedef {Object} WarningPayload
 * @property {string} warningId
 * @property {string} file
 * @property {number} line
 * @property {string} type
 * @property {string} message
 * @property {string} original
 * @property {string | null | undefined} fix
 * @property {string | null | undefined} fixText
 * @property {number | null | undefined} colStart
 * @property {number | null | undefined} colEnd
 * @property {string | null | undefined} highlight
 * @property {Array<string>} imports
 * @property {Array<string>} importsNeeded
 * @property {Object | null | undefined} proposal
 * @property {string | null | undefined} resolutionStatus
 * @property {Object | null | undefined} resolutionDetails
 * @property {Object | null | undefined} metadata
 */

export {};
