(globalThis.TURBOPACK||(globalThis.TURBOPACK=[])).push(["object"==typeof document?document.currentScript:void 0,98832,e=>{"use strict";e.i(83997);var t=e.i(36184);let i=e=>`
\x1b[35m
[Clerk]:\x1b[0m You are running in keyless mode.
You can \x1b[35mclaim your keys\x1b[0m by visiting ${e.claimUrl}
`,a=()=>`
\x1b[35m
[Clerk]:\x1b[0m Your application is running with your claimed keys.
You can safely remove the \x1b[35m.clerk/\x1b[0m from your project.
`,r=function(){if((0,t.isDevelopmentEnvironment)())return e.g.__clerk_internal_keyless_logger||(e.g.__clerk_internal_keyless_logger={__cache:new Map,log:function({cacheKey:e,msg:t}){var i;this.__cache.has(e)&&Date.now()<((null==(i=this.__cache.get(e))?void 0:i.expiresAt)||0)||(console.log(t),this.__cache.set(e,{expiresAt:Date.now()+6e5}))},run:async function(e,{cacheKey:t,onSuccessStale:i=6e5,onErrorStale:a=6e5}){var r,n;if(this.__cache.has(t)&&Date.now()<((null==(r=this.__cache.get(t))?void 0:r.expiresAt)||0))return null==(n=this.__cache.get(t))?void 0:n.data;try{let a=await e();return this.__cache.set(t,{expiresAt:Date.now()+i,data:a}),a}catch(e){throw this.__cache.set(t,{expiresAt:Date.now()+a}),e}}}),globalThis.__clerk_internal_keyless_logger}();e.s(["clerkDevelopmentCache",()=>r,"createConfirmationMessage",()=>a,"createKeylessModeMessage",()=>i])}]);