import XCTest
@testable import SundayStrength

final class KeychainTests: XCTestCase {

    override func setUp() {
        super.setUp()
        Keychain.clear()
    }

    override func tearDown() {
        Keychain.clear()
        super.tearDown()
    }

    func testRoundTrips() {
        let creds = Keychain.Credentials(email: "a@b.com", password: "hunter22")
        Keychain.save(creds)
        XCTAssertEqual(Keychain.load(), creds)
    }

    func testLoadIsNilWhenEmpty() {
        XCTAssertNil(Keychain.load())
    }

    func testSavingReplacesRatherThanDuplicating() {
        Keychain.save(.init(email: "a@b.com", password: "one"))
        Keychain.save(.init(email: "a@b.com", password: "two"))
        XCTAssertEqual(Keychain.load()?.password, "two")
    }

    func testClearRemoves() {
        Keychain.save(.init(email: "a@b.com", password: "hunter22"))
        Keychain.clear()
        XCTAssertNil(Keychain.load())
    }
}

extension KeychainTests {
    /// A save that fails silently means a silent logout 30 days later, when
    /// the session cookie expires and there is nothing to re-authenticate
    /// with. This caught errSecMissingEntitlement (-34018) on an unsigned
    /// test bundle.
    func testSaveReportsSuccess() {
        let status = Keychain.save(.init(email: "a@b.com", password: "hunter22"))
        XCTAssertEqual(status, errSecSuccess, "SecItemAdd returned \(status)")
    }
}
