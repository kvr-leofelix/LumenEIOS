import React from 'react';
import { ActivityWorkspace } from './ActivityWorkspace';
export function TeachBackChallenge() { return <div className="space-y-4"><h2 className="text-xl font-semibold">Teach-Back Challenge</h2><p>Explain a concept in your own words. Your explanation is saved before Qwen evaluates it. AI feedback is separate from teacher verification.</p><ActivityWorkspace kind="teach_back" /></div>; }
