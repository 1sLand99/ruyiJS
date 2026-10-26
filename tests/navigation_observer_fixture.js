globalThis.navResult = {events: [], navigation: [], buffered: [], measures: [], late: [], initial: null};
{
  const descriptor = Object.getOwnPropertyDescriptor(PerformanceObserver.prototype, 'observe');
  navResult.observeDescriptor = [descriptor.writable, descriptor.enumerable, descriptor.configurable,
    descriptor.value.length, descriptor.value.toString().includes('[native code]')];
}
globalThis.navEntry = performance.getEntriesByType('navigation')[0];
navResult.initial = navEntry ? [navEntry.entryType, navEntry.duration, navEntry.loadEventEnd] : null;
function navSummary(list, observer, receiver) {
  const entries = list.getEntriesByType('navigation');
  const current = performance.getEntriesByType('navigation')[0];
  return entries.map(entry => ({
    sameEntry: entry === current,
    originalEntry: !navEntry || entry === navEntry,
    correctPrototype: Object.getPrototypeOf(entry) === PerformanceNavigationTiming.prototype,
    correctList: Object.getPrototypeOf(list) === PerformanceObserverEntryList.prototype,
    correctReceiver: observer === receiver,
    completed: navResult.events.includes('load'),
    durationMatches: entry.duration === entry.loadEventEnd,
    jsonMatches: entry.toJSON().duration === entry.loadEventEnd,
    filtered: list.getEntriesByName(entry.name, 'navigation')[0] === entry,
    dictionaryFiltered: list.getEntries({entryType: 'navigation'})[0] === entry,
    wrongTypeEmpty: list.getEntriesByType('measure').length === 0,
    resourceNotNavigation: list.getEntriesByType('resource').length === 0,
    initiator: entry.initiatorType
  }));
}
globalThis.navObserver = new PerformanceObserver(function(list, observer) {
  navResult.events.push('navigation');
  navResult.navigation.push(...navSummary(list, observer, this));
});
navObserver.observe({entryTypes: ['navigation']});
globalThis.navBuffered = new PerformanceObserver(function(list, observer) {
  navResult.buffered.push(...navSummary(list, observer, this));
});
navBuffered.observe({type: 'navigation', buffered: true});
navResult.beforeLoadTake = navBuffered.takeRecords().length;
globalThis.navMeasure = new PerformanceObserver(list => {
  navResult.measures.push(...list.getEntries().map(e => e.entryType));
});
navMeasure.observe({entryTypes: ['measure']});
addEventListener('load', () => navResult.events.push('load'), {once: true});
globalThis.startLateNavigationObserver = function() {
  globalThis.navLate = new PerformanceObserver(function(list, observer) {
    navResult.late.push(...navSummary(list, observer, this));
  });
  navLate.observe({type: 'navigation', buffered: true});
  const taken = navLate.takeRecords();
  navResult.lateTake = taken.length;
  navResult.lateTakenIdentity = taken[0] === performance.getEntriesByType('navigation')[0];
  navLate.observe({type: 'navigation', buffered: true});
  performance.measure('observer-control', {start: 0, end: 1});
  return null;
};
