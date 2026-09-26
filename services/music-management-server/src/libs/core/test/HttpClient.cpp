/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#include <gtest/gtest.h>

#include <atomic>
#include <chrono>
#include <istream>
#include <iterator>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include <boost/asio/executor_work_guard.hpp>
#include <boost/asio/io_context.hpp>
#include <boost/asio/ip/tcp.hpp>
#include <boost/asio/read.hpp>
#include <boost/asio/read_until.hpp>
#include <boost/asio/streambuf.hpp>
#include <boost/asio/write.hpp>
#include <boost/system/system_error.hpp>

#include "core/String.hpp"
#include "core/http/IClient.hpp"

namespace lms::core::http::tests
{
    namespace
    {
        namespace asio = boost::asio;
        using asio::ip::tcp;

        struct ReceivedRequest
        {
            std::string method;
            std::string target;
            std::string body;
        };

        // A loopback HTTP server that records what arrives on the wire: one connection per
        // expected request, the request line and body kept, a bare 200 sent back. What the
        // client *thinks* it sent is not the question; what the other end reads is.
        class LoopbackServer
        {
        public:
            explicit LoopbackServer(std::size_t expectedRequestCount)
                : _acceptor{ _ioContext, tcp::endpoint{ asio::ip::address_v4::loopback(), 0 } }
                , _thread{ [this, expectedRequestCount] {
                    try
                    {
                        for (std::size_t i{}; i < expectedRequestCount; ++i)
                            serveOne();
                    }
                    catch (const boost::system::system_error&)
                    {
                        // The acceptor was closed under us (see the destructor): stop serving.
                    }
                } }
            {
            }

            ~LoopbackServer()
            {
                // A failed test may leave the thread blocked in accept(); closing the acceptor
                // makes that accept throw, so the test fails instead of hanging the job.
                boost::system::error_code ec;
                _acceptor.close(ec);
                _thread.join();
            }

            std::string getBaseUrl() const
            {
                return "http://127.0.0.1:" + std::to_string(_acceptor.local_endpoint().port());
            }

            std::vector<ReceivedRequest> getReceivedRequests()
            {
                const std::scoped_lock lock{ _mutex };
                return _received;
            }

        private:
            void serveOne()
            {
                tcp::socket socket{ _ioContext };
                _acceptor.accept(socket);

                asio::streambuf buffer;
                asio::read_until(socket, buffer, "\r\n\r\n");
                std::istream stream{ &buffer };

                ReceivedRequest request;
                std::string version;
                stream >> request.method >> request.target >> version;

                std::string line;
                std::getline(stream, line); // the rest of the request line

                std::size_t contentLength{};
                while (std::getline(stream, line) && line != "\r")
                {
                    constexpr std::string_view header{ "content-length:" };
                    if (stringUtils::stringCaseInsensitiveEqual(std::string_view{ line }.substr(0, header.size()), header))
                        contentLength = stringUtils::readAs<std::size_t>(stringUtils::stringTrim(line.substr(header.size()))).value_or(0);
                }

                // read_until may already have pulled part of the body into the buffer.
                request.body.assign(std::istreambuf_iterator<char>{ stream }, std::istreambuf_iterator<char>{});
                if (request.body.size() < contentLength)
                {
                    std::string rest(contentLength - request.body.size(), '\0');
                    asio::read(socket, asio::buffer(rest));
                    request.body += rest;
                }

                const std::string response{ "HTTP/1.1 200 OK\r\nContent-Length: 0\r\nConnection: close\r\n\r\n" };
                asio::write(socket, asio::buffer(response));

                boost::system::error_code ignored;
                socket.shutdown(tcp::socket::shutdown_both, ignored);

                const std::scoped_lock lock{ _mutex };
                _received.push_back(std::move(request));
            }

            asio::io_context _ioContext;
            tcp::acceptor _acceptor;
            std::mutex _mutex;
            std::vector<ReceivedRequest> _received;
            std::thread _thread;
        };

        bool waitUntil(const std::atomic<std::size_t>& counter, std::size_t expected, std::chrono::seconds timeout)
        {
            const auto deadline{ std::chrono::steady_clock::now() + timeout };
            while (counter.load() < expected)
            {
                if (std::chrono::steady_clock::now() > deadline)
                    return false;
                std::this_thread::sleep_for(std::chrono::milliseconds{ 10 });
            }
            return true;
        }

        const ReceivedRequest* findByTarget(const std::vector<ReceivedRequest>& requests, std::string_view target)
        {
            for (const ReceivedRequest& request : requests)
            {
                if (request.target == target)
                    return &request;
            }
            return nullptr;
        }
    } // namespace

    // Every PUT and DELETE handed to the client used to leave as a POST, so a route that only
    // takes the real verb answered 405 for a request the caller never sent. The verb has to be
    // checked on the receiving end: nothing in the client's own bookkeeping would show it.
    // PATCH joined for MuMa's per-key account-settings write (bug report 116).
    TEST(HttpClient, eachVerbReachesTheServerAsItself)
    {
        LoopbackServer server{ 5 };

        asio::io_context ioContext;
        auto work{ asio::make_work_guard(ioContext) };
        std::thread ioThread{ [&ioContext] { ioContext.run(); } };

        std::atomic<std::size_t> completed{};
        std::atomic<std::size_t> failed{};
        {
            // Scoped so the client is torn down while the io_context still runs: its destructor
            // aborts through the strand and waits for that to happen.
            const std::unique_ptr<IClient> client{ createClient(ioContext, server.getBaseUrl()) };

            auto fill = [&](ClientRequestParameters& params, std::string relativeUrl) {
                params.relativeUrl = std::move(relativeUrl);
                params.onSuccessFunc = [&completed](const Wt::Http::Message&) { ++completed; };
                params.onFailureFunc = [&completed, &failed]() {
                    ++failed;
                    ++completed;
                };
            };

            ClientGETRequestParameters get;
            fill(get, "/get");
            client->sendGETRequest(std::move(get));

            ClientPOSTRequestParameters post;
            fill(post, "/post");
            post.message.addBodyText("posted");
            client->sendPOSTRequest(std::move(post));

            ClientPUTRequestParameters put;
            fill(put, "/put");
            put.message.addBodyText("put");
            client->sendPUTRequest(std::move(put));

            ClientDELETERequestParameters del;
            fill(del, "/delete");
            client->sendDELETERequest(std::move(del));

            ClientPATCHRequestParameters patch;
            fill(patch, "/patch");
            patch.message.addBodyText("patched");
            client->sendPATCHRequest(std::move(patch));

            ASSERT_TRUE(waitUntil(completed, 5, std::chrono::seconds{ 30 })) << "only " << completed.load() << " of 5 requests completed";
        }

        work.reset();
        ioContext.stop();
        ioThread.join();

        EXPECT_EQ(failed.load(), 0);

        const std::vector<ReceivedRequest> received{ server.getReceivedRequests() };
        ASSERT_EQ(received.size(), 5);

        const ReceivedRequest* get{ findByTarget(received, "/get") };
        ASSERT_NE(get, nullptr);
        EXPECT_EQ(get->method, "GET");

        const ReceivedRequest* post{ findByTarget(received, "/post") };
        ASSERT_NE(post, nullptr);
        EXPECT_EQ(post->method, "POST");
        EXPECT_EQ(post->body, "posted");

        const ReceivedRequest* put{ findByTarget(received, "/put") };
        ASSERT_NE(put, nullptr);
        EXPECT_EQ(put->method, "PUT");
        EXPECT_EQ(put->body, "put");

        const ReceivedRequest* del{ findByTarget(received, "/delete") };
        ASSERT_NE(del, nullptr);
        EXPECT_EQ(del->method, "DELETE");

        const ReceivedRequest* patch{ findByTarget(received, "/patch") };
        ASSERT_NE(patch, nullptr);
        EXPECT_EQ(patch->method, "PATCH");
        EXPECT_EQ(patch->body, "patched");
    }
} // namespace lms::core::http::tests
