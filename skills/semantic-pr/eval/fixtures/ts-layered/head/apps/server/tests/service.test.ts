import { createIdea } from "../src/service";
export function testCreate(): boolean { return createIdea(" x ").title === "x"; }
