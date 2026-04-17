// Headless parity harness for backend.game.engine vs gorisanson/pikachu-volleyball.
// Runs the original physics.js with a deterministic RNG + scripted inputs and
// dumps per-frame state to JSON. The Python harness consumes the same input
// script and seed and the test compares both dumps frame-for-frame.

import { PikaPhysics, PikaUserInput } from "./physics.js";
import { setCustomRng } from "./rand.js";

// Mulberry32 — bit-exact implementable in Python.
function mulberry32(seed) {
  let s = seed >>> 0;
  return function () {
    s = (s + 0x6D2B79F5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t = (t ^ (t + Math.imul(t ^ (t >>> 7), t | 61))) >>> 0;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const SEED = 12345;
setCustomRng(mulberry32(SEED));

// Construct physics: both players non-computer (engine inputs come from us).
const physics = new PikaPhysics(false, false);

// Deterministic input script for 500 frames. Mix: idle, walk, jump, power-hit,
// dive trigger. Same script used by the Python harness.
function inputAtFrame(i) {
  // Player 1 input
  const p1 = new PikaUserInput();
  if (i % 17 === 0) p1.yDirection = -1;            // jump every 17 frames
  if (i % 23 === 0) p1.xDirection = 1;             // walk right every 23
  if (i % 29 === 0) p1.xDirection = -1;            // walk left every 29
  if (i % 41 === 0) p1.powerHit = 1;               // power-hit every 41
  if (i % 67 === 0) {                              // dive every 67
    p1.xDirection = 1;
    p1.powerHit = 1;
  }
  // Player 2 input — slightly different cadence so both halves get exercised
  const p2 = new PikaUserInput();
  if (i % 19 === 0) p2.yDirection = -1;
  if (i % 31 === 0) p2.xDirection = -1;
  if (i % 37 === 0) p2.xDirection = 1;
  if (i % 43 === 0) p2.powerHit = 1;
  if (i % 71 === 0) {
    p2.xDirection = -1;
    p2.powerHit = 1;
  }
  return [p1, p2];
}

const frames = [];
for (let i = 0; i < 500; i++) {
  const inputs = inputAtFrame(i);
  const isBallTouchingGround = physics.runEngineForNextFrame(inputs);
  frames.push({
    frame: i,
    p1: {
      x: physics.player1.x,
      y: physics.player1.y,
      vy: physics.player1.yVelocity,
      state: physics.player1.state,
      frameNumber: physics.player1.frameNumber,
      lyingDownDurationLeft: physics.player1.lyingDownDurationLeft,
      isCollisionWithBallHappened: physics.player1.isCollisionWithBallHappened,
    },
    p2: {
      x: physics.player2.x,
      y: physics.player2.y,
      vy: physics.player2.yVelocity,
      state: physics.player2.state,
      frameNumber: physics.player2.frameNumber,
      lyingDownDurationLeft: physics.player2.lyingDownDurationLeft,
      isCollisionWithBallHappened: physics.player2.isCollisionWithBallHappened,
    },
    ball: {
      x: physics.ball.x,
      y: physics.ball.y,
      vx: physics.ball.xVelocity,
      vy: physics.ball.yVelocity,
      rotation: physics.ball.rotation,
      fineRotation: physics.ball.fineRotation,
      isPowerHit: physics.ball.isPowerHit,
      expectedLandingPointX: physics.ball.expectedLandingPointX,
    },
    isBallTouchingGround,
  });
}

process.stdout.write(JSON.stringify({ seed: SEED, frames }, null, 0));
