import XCTest
@testable import SundayStrength

final class PhotoCacheTests: XCTestCase {

    private var dir: URL!

    override func setUp() {
        super.setUp()
        dir = FileManager.default.temporaryDirectory
            .appendingPathComponent("photos-\(UUID().uuidString)")
    }

    override func tearDown() {
        StubProtocol.handler = nil
        try? FileManager.default.removeItem(at: dir)
        super.tearDown()
    }

    private func cache() -> PhotoCache {
        PhotoCache(baseURL: URL(string: "http://localhost:8123")!,
                   session: StubProtocol.session(), directory: dir)
    }

    /// Seen once, a photo shows again with no signal.
    func testAPhotoFetchedOnceIsThereOffline() async {
        let asked = LockedBox()
        StubProtocol.handler = { request in
            asked.value = request.url!.absoluteString
            return (HTTPURLResponse(url: request.url!, statusCode: 200,
                                    httpVersion: nil, headerFields: nil)!,
                    Data([1, 2, 3]))
        }
        let first = await cache().data(for: "/static/exercises/plank-0.jpg")
        XCTAssertEqual(first, Data([1, 2, 3]))
        XCTAssertEqual(asked.value,
                       "http://localhost:8123/static/exercises/plank-0.jpg")

        StubProtocol.handler = { _ in throw URLError(.notConnectedToInternet) }
        let offline = await cache().data(for: "/static/exercises/plank-0.jpg")
        XCTAssertEqual(offline, Data([1, 2, 3]))
    }

    func testAPhotoNeverSeenIsNilOffline() async {
        StubProtocol.handler = { _ in throw URLError(.notConnectedToInternet) }
        let data = await cache().data(for: "/static/exercises/plank-1.jpg")
        XCTAssertNil(data)
    }

    /// A 404 page must not be saved and shown as a photo.
    func testAnErrorPageIsNotKept() async {
        StubProtocol.handler = { request in
            (HTTPURLResponse(url: request.url!, statusCode: 404, httpVersion: nil,
                             headerFields: nil)!, Data("Not Found".utf8))
        }
        let data = await cache().data(for: "/static/exercises/nope-0.jpg")
        XCTAssertNil(data)
    }
}
